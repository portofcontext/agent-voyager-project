/**
 * OpenCode session events -> Recorder calls.
 *
 * OpenCode makes one model request per assistant message, bracketed by a
 * `step-start` and a `step-finish` part; the `step-finish` part carries that
 * request's tokens. So each root-session `step-finish` is reported as one
 * turn: the message's text, reasoning, and tool parts as content, the step's
 * tokens as usage. OpenCode runs a step's tools before the step finishes, so
 * their results usually follow the turn at once; a result that lands later is
 * reported when its part completes. Reporting after the fact, the Recorder's
 * clock is pinned to OpenCode's own timestamps (`EventClock`), so event times
 * and tool durations are the real ones.
 *
 * The `task` tool runs a subagent in a child session. Its frame opens and
 * closes around the task call; the child's own requests (and any
 * grandchildren's) are rolled up onto `subagent_returned` as `SubagentUsage`,
 * since the Recorder places every turn under the agent span.
 *
 * Cost is computed from the AVP price table, not taken from OpenCode's
 * `cost`, so it is reproducible from the trajectory.
 */
import { computeCost, type Clock, type ContentBlock, type PriceTable, type Recorder } from "@avp/types";
import type { ErrorCode, SubagentUsage } from "@avp/types/trajectory";
import type { AssistantMessage, Event, Part, StepFinishPart, ToolPart } from "@opencode-ai/sdk/v2/client";

import * as translate from "./translate.js";

export interface TranslatorOptions {
  /** Maps OpenCode's tool name to the AVP name. */
  toolName: (name: string) => string;
  /** The Commission's model id, the price-table fallback. */
  requestModel: string;
  /** The origin the price table keys models under. */
  provider: string;
  prices: PriceTable;
  /** OpenCode asked for a permission; the run is sandboxed, so it is granted. */
  onPermission: (requestID: string) => void;
  /** OpenCode is retrying a request that can't succeed; stop it. */
  onHopeless: () => void;
}

/**
 * The Recorder's clock: wall time, or a past instant while reporting what
 * OpenCode did then. It never runs backwards, so event times stay in
 * emission order.
 */
export class EventClock implements Clock {
  private pinned: number | undefined;
  private last = 0;

  /** Run `fn` with the clock reading `epochMs` (or later, to stay monotonic). */
  at<T>(epochMs: number | undefined, fn: () => T): T {
    this.pinned = epochMs;
    try {
      return fn();
    } finally {
      this.pinned = undefined;
    }
  }

  nowIso(): string {
    return new Date(this.now()).toISOString();
  }

  monotonic(): number {
    return this.now() / 1000;
  }

  private now(): number {
    this.last = Math.max(this.pinned ?? Date.now(), this.last);
    return this.last;
  }
}

interface Message {
  sessionID: string;
  info?: AssistantMessage;
  parts: Map<string, Part>;
  reported: Set<string>;
}

interface Spend {
  cost: number;
  priced: boolean;
  input: number;
  output: number;
  turns: number;
  text: string;
}

export class SessionTranslator {
  /** The first provider failure on the root session, if any. */
  error: [ErrorCode, string] | undefined;
  /** True once the root session is idle. */
  idle = false;

  private readonly parents = new Map<string, string>();
  private readonly messages = new Map<string, Message>();
  private readonly pending = new Set<string>();
  /** Task call id -> its child session, once OpenCode reports it. */
  private readonly children = new Map<string, string>();
  private readonly opened = new Set<string>();
  private readonly spend = new Map<string, Spend>();
  private last: Message | undefined;

  constructor(
    private readonly rec: Recorder,
    private readonly clock: EventClock,
    readonly root: string,
    private readonly opts: TranslatorOptions,
  ) {}

  handle(event: Event): void {
    switch (event.type) {
      case "session.created":
      case "session.updated":
        if (event.properties.info.parentID) this.parents.set(event.properties.info.id, event.properties.info.parentID);
        return;
      case "message.updated": {
        const info = event.properties.info;
        if (info.role !== "assistant") return;
        const message = this.message(info.id, info.sessionID);
        message.info = info;
        if (info.sessionID === this.root) this.last = message;
        return;
      }
      case "message.part.updated":
        return this.part(event.properties.part);
      case "message.part.delta": {
        // Streamed text arrives as deltas; a cut-off request never gets its final part update.
        const { messageID, partID, field, delta } = event.properties;
        const part = this.messages.get(messageID)?.parts.get(partID) as Record<string, unknown> | undefined;
        if (part && typeof part[field] === "string") part[field] += delta;
        return;
      }
      case "session.status": {
        const { sessionID, status } = event.properties;
        if (sessionID === this.root && status.type === "retry" && translate.hopelessRetry(status.message)) {
          this.error ??= [translate.messageCode(status.message), status.message];
          this.opts.onHopeless();
        }
        return;
      }
      case "session.error": {
        const { sessionID, error } = event.properties;
        if (error && (sessionID === undefined || sessionID === this.root) && error.name !== "MessageAbortedError") {
          this.error ??= [translate.errorCode(error), translate.errorMessage(error)];
        }
        return;
      }
      case "permission.asked":
        this.opts.onPermission(event.properties.id);
        return;
      case "session.idle":
        if (event.properties.sessionID === this.root) this.idle = true;
        return;
    }
  }

  /** The root session's final failure, from its last assistant message. */
  get lastError(): [ErrorCode, string] | undefined {
    const error = this.last?.info?.error;
    if (!error || error.name === "MessageAbortedError") return undefined;
    return [translate.errorCode(error), translate.errorMessage(error)];
  }

  /** The root session's final answer: its structured output, else its last message's text. */
  get output(): unknown {
    if (this.last?.info?.structured !== undefined) return this.last.info.structured;
    return text(this.last) || undefined;
  }

  /**
   * After an interrupt: report what the cut-off request produced (its text,
   * and any tool calls that finished), without usage.
   */
  flushInterrupted(): void {
    const message = this.last;
    if (!message || message.info?.finish) return;
    const parts = [...message.parts.values()].filter(
      (p) => !message.reported.has(p.id) && (p.type !== "tool" || translate.toolResult(p) !== undefined),
    );
    this.report(message, parts, undefined, ["aborted"]);
  }

  private part(part: Part): void {
    const message = this.message(part.messageID, part.sessionID);
    message.parts.set(part.id, part);
    if (part.type === "tool") {
      const child = part.tool === "task" && "metadata" in part.state ? part.state.metadata?.sessionId : undefined;
      if (typeof child === "string") this.children.set(part.callID, child);
      if (this.pending.has(part.callID) && translate.toolResult(part)) this.result(part);
    } else if (part.type === "step-finish") {
      if (part.sessionID === this.root) {
        const parts = [...message.parts.values()].filter((p) => !message.reported.has(p.id));
        this.report(message, parts, part, [part.reason]);
      } else {
        this.rollUp(message, part);
      }
    }
  }

  private report(message: Message, parts: Part[], finish: StepFinishPart | undefined, reasons: string[]): void {
    const content: ContentBlock[] = [];
    const tools: ToolPart[] = [];
    // The response is complete when its last text ends or its last tool call starts running.
    let done = 0;
    for (const p of parts) {
      message.reported.add(p.id);
      const block = translate.block(p, this.opts.toolName);
      if (block) content.push(block);
      if (p.type === "tool") tools.push(p);
      done = Math.max(done, endOf(p) ?? 0);
    }
    const created = message.info?.time.created;
    const at = done || Date.now();
    this.clock.at(at, () =>
      this.rec.assistant(content, finish ? translate.usage(finish.tokens) : undefined, {
        model: message.info?.modelID ?? this.opts.requestModel,
        requestModel: this.opts.requestModel,
        finishReasons: reasons,
        durationMs: created ? Math.max(0, at - created) : undefined,
      }),
    );
    for (const tool of tools) {
      this.pending.add(tool.callID);
      if (tool.tool === "task") {
        const input = tool.state.input as { subagent_type?: string; description?: string };
        this.clock.at(started(tool), () =>
          this.rec.subagentStart(tool.callID, input.subagent_type ?? "task", { description: input.description }),
        );
        this.opened.add(tool.callID);
      }
    }
    // Parallel calls finish in any order; report results as they finished, so
    // each lands at its own end time on the monotonic clock.
    const finished = tools.filter((t) => translate.toolResult(t)).sort((a, b) => (ended(a) ?? 0) - (ended(b) ?? 0));
    for (const tool of finished) this.result(tool);
  }

  private result(tool: ToolPart): void {
    const result = translate.toolResult(tool)!;
    this.pending.delete(tool.callID);
    this.clock.at(ended(tool), () => {
      if (this.opened.delete(tool.callID)) {
        const child = this.children.get(tool.callID);
        const spend = child ? this.spend.get(child) : undefined;
        this.rec.subagentResult(tool.callID, spend?.text || result.text, {
          reason: result.isError ? "error" : "converged",
          usage: spend ? subagentUsage(spend) : undefined,
        });
      }
      this.rec.toolResult(tool.callID, result.text, { isError: result.isError });
    });
  }

  /** Add a child-session request to the spend of the root's direct child it descends from. */
  private rollUp(message: Message, finish: StepFinishPart): void {
    let child = message.sessionID;
    for (let parent = this.parents.get(child); parent && parent !== this.root; parent = this.parents.get(child)) {
      child = parent;
    }
    if (this.parents.get(child) !== this.root) return;
    const spend = this.spend.get(child) ?? { cost: 0, priced: true, input: 0, output: 0, turns: 0, text: "" };
    this.spend.set(child, spend);
    const usage = translate.usage(finish.tokens);
    let priced: [number, string] = [0, "unknown"];
    for (const model of new Set([message.info?.modelID, this.opts.requestModel])) {
      if (!model || priced[1] !== "unknown") continue;
      priced = computeCost(
        this.opts.provider,
        model,
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_input_tokens ?? 0,
        usage.cache_creation_input_tokens ?? 0,
        this.opts.prices,
      );
    }
    spend.cost += priced[0];
    spend.priced &&= priced[1] !== "unknown";
    spend.input += usage.input_tokens;
    spend.output += usage.output_tokens;
    spend.turns += 1;
    if (message.sessionID === child) spend.text = text(message) || spend.text;
  }

  private message(id: string, sessionID: string): Message {
    let message = this.messages.get(id);
    if (!message) {
      message = { sessionID, parts: new Map(), reported: new Set() };
      this.messages.set(id, message);
    }
    return message;
  }
}

/** When a part's model output was complete: a text or reasoning end, or a tool call starting to run. */
function endOf(part: Part): number | undefined {
  if (part.type === "text" || part.type === "reasoning") return part.time?.end;
  if (part.type === "tool") return started(part);
  return undefined;
}

function started(tool: ToolPart): number | undefined {
  return "time" in tool.state ? tool.state.time.start : undefined;
}

function ended(tool: ToolPart): number | undefined {
  return "time" in tool.state && "end" in tool.state.time ? tool.state.time.end : undefined;
}

function text(message: Message | undefined): string {
  if (!message) return "";
  return [...message.parts.values()]
    .filter((p): p is Extract<Part, { type: "text" }> => p.type === "text" && !p.synthetic && !p.ignored)
    .map((p) => p.text)
    .join("");
}

function subagentUsage(spend: Spend): SubagentUsage {
  return {
    ...(spend.priced ? { cost_usd: spend.cost } : {}),
    tokens_input: spend.input,
    tokens_output: spend.output,
    turns: spend.turns,
  };
}
