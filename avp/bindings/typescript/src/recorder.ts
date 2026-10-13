/**
 * The trajectory's ordering and span rules, in one place.
 *
 * An adapter reports what its harness did; the `Recorder` decides what goes
 * on the wire and in what order. It is a plain object the adapter calls: no
 * base class, no agent loop, no callbacks into the adapter.
 *
 * ```ts
 * const rec = new Recorder(new FileSink(out), { provider: "anthropic" });
 * rec.prelude(commission, descriptor);              // run_requested, agent_described
 * rec.start({ requestModel, tools });               // agent_started
 * rec.assistant(content, usage, { model });         // assistant_message + tool_invoked
 * rec.toolResult("call_1", "ok");                   // tool_returned
 * rec.stop("converged");                            // agent_stopped
 * ```
 *
 * The rules match the Python `avp.recorder.Recorder` and the Rust
 * `avp::recorder::Recorder`, and are pinned by the shared vectors under
 * `avp/core/conformance/src/avp_conformance/recorder/v0.1/` (run by
 * `tests/recorder-vectors.test.ts`):
 *
 * - Span tree: agent span, then turn span, then `tool_invoked`, then
 *   `tool_returned`; subagent frames sit beside `tool_invoked` under the turn.
 * - Step counter: a turn with no output (no content beyond empty text, no
 *   events) is not put on the wire and does not consume a step.
 * - Turn buffering: `assistant_message` first, then everything reported while
 *   the turn was open, in arrival order, each with the time it was reported.
 *   The `assistant_message` is stamped with its last chunk's time.
 * - Turn delivery: chunks under the same `turnKey` merge until one of the
 *   turn's tool calls returns; a new key or no key closes the open turn, and a
 *   keyless turn closes at once.
 * - `tool_invoked` comes from the `tool_use` / `server_tool_use` blocks in an
 *   assistant turn's content; `tool_returned` pairs by call id.
 * - Subagent frames are run-scoped; frames open at stop close as `abandoned`
 *   and a `converged` stop downgrades to `abandoned`.
 * - Cost: `reported` when the adapter passes one, `unknown` for an unpriced
 *   model or a turn with no token counts, else `computed` from the price table.
 * - `stop` is idempotent; `error` parents under the agent span once started.
 * - Invalid adapter reports throw `RecorderError`: unknown or duplicate IDs,
 *   mismatched usage, repeated prelude/start, and reports after stop. Rejected
 *   reports leave valid state intact. `stop` and an empty `closeTurn` remain
 *   safe cleanup calls.
 */
import type { Commission, Event } from "./index.js";
import { newEventId, newSpanId, newTraceId, nowIso, SOURCE_AGENT, ZERO_SPAN_ID } from "./ids.js";
import { computeCost, type CostSource, type PriceTable } from "./pricing.js";
import type { Sink } from "./sink.js";
import type {
  AgentDescriptor,
  AvpContent,
  ErrorCode,
  McpServerDecl,
  SkillDecl,
  StopReason,
  SubagentDecl,
  SubagentUsage,
  ToolDecl,
  ToolResultBlock,
  Usage,
} from "./trajectory.js";

export type ContentBlock = AvpContent[number];
export type DispatchTarget = "mcp_server" | "local";

/** Text carried by a subagent frame the Recorder closes at stop. */
export const ABANDONED_SUBAGENT_TEXT =
  "Run ended while this subagent was still running; it never reported a result.";

/** An invalid adapter report. The Recorder's state is unchanged. */
export class RecorderError extends Error {
  override name = "RecorderError";
}

/** Time source. `nowIso` stamps event `time`; `monotonic` (seconds) drives every `duration_ms`. */
export interface Clock {
  nowIso(): string;
  monotonic(): number;
}

/** Id source for the trace, spans, and CloudEvents `id`. */
export interface Ids {
  traceId(): string;
  spanId(): string;
  eventId(): string;
}

export class SystemClock implements Clock {
  nowIso(): string {
    return nowIso();
  }
  monotonic(): number {
    return performance.now() / 1000;
  }
}

export class RandomIds implements Ids {
  traceId(): string {
    return newTraceId();
  }
  spanId(): string {
    return newSpanId();
  }
  eventId(): string {
    return newEventId();
  }
}

/** Constructor inputs. Everything is optional. */
export interface RecorderOptions {
  /** CloudEvents `subject` on every event; a fresh UUID if omitted. */
  runId?: string;
  /** `avp.provider.name`, and the provider bare model names resolve under in `prices`. */
  provider?: string;
  /** Price table for computed cost. Empty means every turn is `unknown` unless the adapter reports a cost. */
  prices?: PriceTable;
  /** Classifies a tool name. Defaults to the catalog passed to `start` (a decl with `avp.mcp_server_id` is MCP). */
  dispatchTarget?: (name: string) => DispatchTarget;
  clock?: Clock;
  ids?: Ids;
}

/** `agent_started` inputs. `tools` is also the dispatch-target catalog. */
export interface StartInfo {
  requestModel?: string;
  prompt?: string;
  systemPrompt?: string;
  tools?: ToolDecl[];
  mcpServers?: McpServerDecl[];
  skills?: SkillDecl[];
  subagents?: SubagentDecl[];
  sessionId?: string;
  threadId?: string;
  tags?: string[];
  meta?: Record<string, unknown>;
}

/**
 * Per-chunk extras for `assistant`. `model` is the response model:
 * `avp.response.model` on the wire and the price-table key; when the table
 * doesn't know it, cost is computed for `requestModel` instead. Within a turn
 * `finishReasons`, `costUsd`, and `durationMs` are last-write-wins, `model`
 * and `requestModel` first-write-wins, and `meta` keys merge.
 */
export interface AssistantOpts {
  model?: string;
  requestModel?: string;
  turnKey?: string;
  finishReasons?: string[];
  meta?: Record<string, unknown>;
  costUsd?: number;
  durationMs?: number;
}

export interface UsageOpts {
  turnKey?: string;
  costUsd?: number;
  durationMs?: number;
}

export interface ToolResultOpts {
  isError?: boolean;
  structuredContent?: Record<string, unknown>;
}

export interface SubagentStartOpts {
  input?: Record<string, unknown>;
  description?: string;
}

export interface SubagentResultOpts {
  reason?: StopReason;
  usage?: SubagentUsage;
  structured?: unknown;
}

type Json = Record<string, unknown>;
type Block = Json & { type?: string };

interface Call {
  spanId: string;
  turnSpanId: string;
  step: number;
  name: string;
  input: unknown;
  startedAt: number;
}

interface Frame {
  spanId: string;
  parentSpanId: string;
  step: number;
  name: string;
  startedAt: number;
}

interface Turn {
  key: string | undefined;
  step: number;
  spanId: string;
  openedAt: number;
  lastChunkAt: number;
  lastChunkIso: string;
  content: Block[];
  usage: Usage | undefined;
  responseModel: string | undefined;
  requestModel: string | undefined;
  finishReasons: string[] | undefined;
  meta: Json;
  costUsd: number | undefined;
  durationMs: number | undefined;
  emissions: Json[];
  callIds: Set<string>;
  toolResulted: boolean;
}

function hasOutput(turn: Turn): boolean {
  return (
    turn.emissions.length > 0 ||
    turn.content.some((b) => !(b.type === "text" && !b.text))
  );
}

/** Drop `null` / `undefined` members, as the other bindings omit `None`. */
function stripNulls(data: Json): Json {
  const out: Json = {};
  for (const [k, v] of Object.entries(data)) {
    if (v !== null && v !== undefined) out[k] = v;
  }
  return out;
}

/** Builds one run's trajectory from what the adapter reports. */
export class Recorder {
  readonly runId: string;
  readonly traceId: string;
  readonly provider: string | undefined;

  private readonly sink: Sink;
  private readonly clock: Clock;
  private readonly ids: Ids;
  private readonly prices: PriceTable;
  private readonly dispatchOverride: ((name: string) => DispatchTarget) | undefined;
  private catalog = new Map<string, boolean>();
  private agentSpanId: string | undefined;
  private turn: Turn | undefined;
  private lastStep = 0;
  private readonly calls = new Map<string, Call>();
  private readonly openCalls = new Set<string>();
  private readonly frames = new Map<string, Frame>();
  private readonly frameIds = new Set<string>();
  private preludeEmitted = false;
  private _stopped = false;

  constructor(sink: Sink, opts: RecorderOptions = {}) {
    this.sink = sink;
    this.clock = opts.clock ?? new SystemClock();
    this.ids = opts.ids ?? new RandomIds();
    this.runId = opts.runId ?? this.ids.eventId();
    this.traceId = this.ids.traceId();
    this.provider = opts.provider;
    this.prices = opts.prices ?? {};
    this.dispatchOverride = opts.dispatchTarget;
  }

  get stopped(): boolean {
    return this._stopped;
  }

  // ── validation ───────────────────────────────────────────────────────

  private requireActive(operation: string, started: boolean): void {
    if (this._stopped) throw new RecorderError(`Recorder.${operation} called after stop`);
    if (started && this.agentSpanId === undefined) {
      throw new RecorderError(`Recorder.${operation} called before start`);
    }
  }

  private requireOpenCall(callId: string): void {
    if (!this.openCalls.has(callId)) {
      const detail = this.calls.has(callId)
        ? `call_id ${callId} already returned`
        : `unknown call_id ${callId}`;
      throw new RecorderError(`Recorder.tool_result: ${detail}`);
    }
  }

  private validateContent(blocks: Block[]): void {
    // Check the whole batch before flushing or accepting any part of it.
    const newCalls = new Set<string>();
    const returned = new Set<string>();
    for (const block of blocks) {
      if (block.type === "tool_use" || block.type === "server_tool_use") {
        const id = String(block.id ?? "");
        if (this.calls.has(id) || newCalls.has(id)) {
          throw new RecorderError(`Recorder.assistant: duplicate call_id ${id}`);
        }
        newCalls.add(id);
      } else if (block.type === "server_tool_result") {
        const id = String(block.tool_use_id ?? "");
        if (returned.has(id)) {
          throw new RecorderError(`Recorder.tool_result: call_id ${id} already returned`);
        }
        returned.add(id);
        if (!newCalls.has(id)) this.requireOpenCall(id);
      }
    }
  }

  // ── envelope ─────────────────────────────────────────────────────────

  private event(type: string, time: string, span: string, parent: string, data: Json): Json {
    return {
      specversion: "1.0",
      id: this.ids.eventId(),
      time,
      subject: this.runId,
      datacontenttype: "application/json",
      type: `avp.${type}`,
      source: SOURCE_AGENT,
      data: {
        trace_id: this.traceId,
        span_id: span,
        parent_span_id: parent,
        ...stripNulls(data),
      },
    };
  }

  private nowEvent(type: string, span: string, parent: string, data: Json): Json {
    return this.event(type, this.clock.nowIso(), span, parent, data);
  }

  private write(event: Json): void {
    this.sink.emit(event as unknown as Event);
  }

  private emitOrBuffer(event: Json): void {
    if (this.turn) this.turn.emissions.push(event);
    else this.write(event);
  }

  private elapsedMs(since: number): number {
    return Math.max(0, Math.trunc((this.clock.monotonic() - since) * 1000));
  }

  private agentParent(): string {
    return this.agentSpanId ?? ZERO_SPAN_ID;
  }

  // ── lifecycle ────────────────────────────────────────────────────────

  /** Emit `run_requested` (with the Commission and its supervisor attribution) then `agent_described`. */
  prelude(commission: Commission | null | undefined, descriptor: AgentDescriptor): void {
    this.requireActive("prelude", false);
    if (this.agentSpanId !== undefined) {
      throw new RecorderError("Recorder.prelude called after start");
    }
    if (this.preludeEmitted) {
      throw new RecorderError("Recorder.prelude called more than once");
    }
    this.preludeEmitted = true;
    const supervisor = commission?.supervisor ?? undefined;
    this.write(
      this.nowEvent("run_requested", this.ids.spanId(), ZERO_SPAN_ID, {
        "avp.supervisor.name": supervisor?.name,
        "avp.supervisor.version": supervisor?.version,
        "avp.commission": commission,
      }),
    );
    this.write(
      this.nowEvent("agent_described", this.ids.spanId(), ZERO_SPAN_ID, {
        "avp.descriptor": descriptor,
      }),
    );
  }

  /** Emit `agent_started` and open the agent span. */
  start(info: StartInfo = {}): void {
    this.requireActive("start", false);
    if (this.agentSpanId !== undefined) {
      throw new RecorderError("Recorder.start called more than once");
    }
    const span = this.ids.spanId();
    this.agentSpanId = span;
    this.catalog = new Map(
      (info.tools ?? []).map((t) => [t.name, Boolean(t["avp.mcp_server_id"])]),
    );
    const meta = info.meta && Object.keys(info.meta).length > 0 ? info.meta : undefined;
    this.write(
      this.nowEvent("agent_started", span, ZERO_SPAN_ID, {
        "avp.meta": meta,
        "avp.provider.name": this.provider,
        "avp.operation.name": "invoke_agent",
        "avp.request.model": info.requestModel,
        "avp.prompt": info.prompt,
        "avp.system_prompt": info.systemPrompt,
        "avp.tools": info.tools,
        "avp.mcp_servers": info.mcpServers,
        "avp.skills": info.skills,
        "avp.subagents": info.subagents,
        "avp.session_id": info.sessionId,
        "avp.thread_id": info.threadId,
        "avp.tags": info.tags,
      }),
    );
  }

  /**
   * Report `error_occurred` under the agent span (the root before `start`).
   * Like every event reported while a turn is open, it lands after that
   * turn's `assistant_message`. Not terminal; follow with `stop`.
   */
  error(code: ErrorCode, message: string): void {
    this.requireActive("error", false);
    this.emitOrBuffer(
      this.nowEvent("error_occurred", this.ids.spanId(), this.agentParent(), {
        "avp.error.code": code,
        "avp.error.message": message,
      }),
    );
  }

  /**
   * Close the open turn and any open subagent frames, then emit
   * `agent_stopped`. Idempotent: only the first call emits.
   */
  stop(reason: StopReason, output?: unknown): void {
    if (this._stopped) return;
    this._stopped = true;
    this.closeTurn();
    if (this.frames.size > 0) {
      for (const id of [...this.frames.keys()]) {
        this.closeFrame(id, ABANDONED_SUBAGENT_TEXT, { reason: "abandoned" });
      }
      if (reason === "converged") reason = "abandoned";
    }
    this.write(
      this.nowEvent("agent_stopped", this.ids.spanId(), this.agentParent(), {
        "avp.reason": reason,
        "avp.output": output,
      }),
    );
  }

  // ── turns ────────────────────────────────────────────────────────────

  /** Report model output for one inference (or one chunk of it). */
  assistant(content: ContentBlock[], usage?: Usage | null, opts: AssistantOpts = {}): void {
    this.requireActive("assistant", true);
    const blocks = content as unknown as Block[];
    this.validateContent(blocks);
    const merge =
      this.turn !== undefined &&
      opts.turnKey !== undefined &&
      !this.turn.toolResulted &&
      this.turn.key === opts.turnKey;
    if (!merge) this.closeTurn();
    const now = this.clock.monotonic();
    const nowIsoStamp = this.clock.nowIso();
    if (!this.turn) {
      this.turn = {
        key: opts.turnKey,
        step: this.lastStep + 1,
        spanId: this.ids.spanId(),
        openedAt: now,
        lastChunkAt: now,
        lastChunkIso: nowIsoStamp,
        content: [],
        usage: undefined,
        responseModel: undefined,
        requestModel: undefined,
        finishReasons: undefined,
        meta: {},
        costUsd: undefined,
        durationMs: undefined,
        emissions: [],
        callIds: new Set(),
        toolResulted: false,
      };
    }
    const turn = this.turn;
    turn.lastChunkAt = now;
    turn.lastChunkIso = nowIsoStamp;
    turn.content.push(...blocks);
    if (usage) turn.usage = usage;
    turn.responseModel ??= opts.model;
    turn.requestModel ??= opts.requestModel;
    if (opts.finishReasons !== undefined) turn.finishReasons = opts.finishReasons;
    if (opts.meta) Object.assign(turn.meta, opts.meta);
    if (opts.costUsd !== undefined) turn.costUsd = opts.costUsd;
    if (opts.durationMs !== undefined) turn.durationMs = opts.durationMs;
    for (const block of blocks) {
      if (block.type === "tool_use" || block.type === "server_tool_use") {
        this.invoke(String(block.id ?? ""), String(block.name ?? ""), block.input);
      } else if (block.type === "server_tool_result") {
        const id = String(block.tool_use_id ?? "");
        this.toolResult(id, {
          type: "tool_result",
          tool_use_id: id,
          content: resultContent(block.content),
          is_error: Boolean(block.is_error ?? false),
        });
      }
    }
    if (opts.turnKey === undefined) this.closeTurn();
  }

  /**
   * Report usage for the open turn after its content, for harnesses that
   * deliver token counts once the inference (or its tool round) is over. Keep
   * the turn open with a `turnKey` until then. Applies to the open turn when
   * `turnKey` is omitted or matches it. A missing or mismatched turn throws
   * `RecorderError`; closed turns cannot accept usage.
   */
  usage(usage: Usage, opts: UsageOpts = {}): void {
    this.requireActive("usage", true);
    const turn = this.turn;
    if (!turn) throw new RecorderError("Recorder.usage: no open turn");
    if (opts.turnKey !== undefined && turn.key !== opts.turnKey) {
      throw new RecorderError(
        `Recorder.usage: turn_key ${opts.turnKey} does not match open turn ${turn.key ?? "None"}`,
      );
    }
    turn.usage = usage;
    if (opts.costUsd !== undefined) turn.costUsd = opts.costUsd;
    if (opts.durationMs !== undefined) turn.durationMs = opts.durationMs;
  }

  private invoke(callId: string, name: string, input: unknown): void {
    const turn = this.turn!;
    const span = this.ids.spanId();
    const target = this.dispatchTarget(name);
    const startedAt = this.clock.monotonic();
    const event = this.nowEvent("tool_invoked", span, turn.spanId, {
      "avp.step": turn.step,
      "avp.tool.call_id": callId,
      "avp.tool.name": name,
      "avp.tool.input": input,
      "avp.tool.dispatch_target": target,
    });
    turn.callIds.add(callId);
    turn.emissions.push(event);
    this.openCalls.add(callId);
    this.calls.set(callId, {
      spanId: span,
      turnSpanId: turn.spanId,
      step: turn.step,
      name,
      input,
      startedAt,
    });
  }

  private dispatchTarget(name: string): DispatchTarget {
    if (this.dispatchOverride) return this.dispatchOverride(name);
    return this.catalog.get(name) ? "mcp_server" : "local";
  }

  /**
   * Close the open turn now: its `assistant_message` (with cost), then its
   * buffered events. A turn with no output emits nothing and frees its step.
   * No-op when no turn is open.
   */
  closeTurn(): void {
    const turn = this.turn;
    if (!turn) return;
    this.turn = undefined;
    if (!hasOutput(turn)) return;
    this.lastStep = turn.step;
    const usage: Usage = turn.usage ?? { input_tokens: 0, output_tokens: 0 };
    let costUsd = 0;
    let costSource: CostSource = "unknown";
    if (turn.costUsd !== undefined) {
      [costUsd, costSource] = [turn.costUsd, "reported"];
    } else if (usage.input_tokens !== 0 || usage.output_tokens !== 0) {
      // Providers often answer with a dated snapshot id the table lacks
      // (`gpt-4o-mini-2024-07-18`); price it as the requested model then.
      const candidates = [...new Set([turn.responseModel, turn.requestModel])];
      for (const model of candidates) {
        if (!model) continue;
        const [cost, source] = computeCost(
          this.provider,
          model,
          usage.input_tokens,
          usage.output_tokens,
          usage.cache_read_input_tokens ?? 0,
          usage.cache_creation_input_tokens ?? 0,
          this.prices,
        );
        if (source !== "unknown") {
          [costUsd, costSource] = [cost, source];
          break;
        }
      }
    }
    const durationMs =
      turn.durationMs ?? Math.max(0, Math.trunc((turn.lastChunkAt - turn.openedAt) * 1000));
    this.write(
      this.event("assistant_message", turn.lastChunkIso, turn.spanId, this.agentParent(), {
        "avp.meta": Object.keys(turn.meta).length > 0 ? turn.meta : undefined,
        "avp.step": turn.step,
        "avp.duration_ms": durationMs,
        "avp.content": turn.content,
        "avp.provider.name": this.provider,
        "avp.request.model": turn.requestModel ?? turn.responseModel,
        "avp.response.model": turn.responseModel,
        "avp.response.finish_reasons": turn.finishReasons,
        "avp.usage": usage,
        "avp.cost_usd": costUsd,
        "avp.cost.source": costSource,
      }),
    );
    for (const event of turn.emissions) this.write(event);
  }

  // ── tools ────────────────────────────────────────────────────────────

  /**
   * Report the result of a tool call seen in assistant content. `content` is
   * the `ToolResultBlock.content` (a string or an array of blocks), or a whole
   * `tool_result` block. Unknown/returned IDs and a mismatched `tool_use_id`
   * throw `RecorderError`.
   */
  toolResult(
    callId: string,
    content: string | unknown[] | ToolResultBlock,
    opts: ToolResultOpts = {},
  ): void {
    this.requireActive("tool_result", true);
    this.requireOpenCall(callId);
    const whole = isResultBlock(content);
    if (whole && content.tool_use_id !== callId) {
      throw new RecorderError(
        `Recorder.tool_result: result tool_use_id ${content.tool_use_id} does not match call_id ${callId}`,
      );
    }
    const block = whole
      ? content
      : stripNulls({
          type: "tool_result",
          tool_use_id: callId,
          content,
          structured_content: opts.structuredContent,
          is_error: opts.isError ?? false,
        });
    const call = this.calls.get(callId)!;
    this.openCalls.delete(callId);
    const event = this.nowEvent("tool_returned", this.ids.spanId(), call.spanId, {
      "avp.step": call.step,
      "avp.tool.call_id": callId,
      "avp.tool.name": call.name,
      "avp.duration_ms": this.elapsedMs(call.startedAt),
      "avp.tool_result": block,
    });
    if (this.turn?.callIds.has(callId)) this.turn.toolResulted = true;
    this.emitOrBuffer(event);
  }

  // ── subagents ────────────────────────────────────────────────────────

  /**
   * Open a subagent frame. When `invocationId` is a tool call seen in
   * assistant content, the frame sits under that call's turn and defaults its
   * input to the call's input.
   */
  subagentStart(invocationId: string, name: string, opts: SubagentStartOpts = {}): void {
    this.requireActive("subagent_start", true);
    if (this.frameIds.has(invocationId)) {
      throw new RecorderError(`Recorder.subagent_start: duplicate invocation_id ${invocationId}`);
    }
    const call = this.calls.get(invocationId);
    let parent: string;
    let step: number;
    let input: unknown;
    if (call) {
      [parent, step, input] = [call.turnSpanId, call.step, opts.input ?? call.input];
    } else if (this.turn) {
      [parent, step, input] = [this.turn.spanId, this.turn.step, opts.input ?? {}];
    } else {
      [parent, step, input] = [this.agentParent(), this.lastStep, opts.input ?? {}];
    }
    const span = this.ids.spanId();
    this.frameIds.add(invocationId);
    this.frames.set(invocationId, {
      spanId: span,
      parentSpanId: parent,
      step,
      name,
      startedAt: this.clock.monotonic(),
    });
    this.emitOrBuffer(
      this.nowEvent("subagent_invoked", span, parent, {
        "avp.step": step,
        "avp.subagent.name": name,
        "avp.subagent.description": opts.description,
        "avp.subagent.invocation_id": invocationId,
        "avp.subagent.input": input,
      }),
    );
  }

  /** Close a subagent frame. Unknown/closed IDs throw `RecorderError`. */
  subagentResult(invocationId: string, text: string, opts: SubagentResultOpts = {}): void {
    this.requireActive("subagent_result", true);
    if (!this.frames.has(invocationId)) {
      const detail = this.frameIds.has(invocationId)
        ? `invocation_id ${invocationId} already returned`
        : `unknown invocation_id ${invocationId}`;
      throw new RecorderError(`Recorder.subagent_result: ${detail}`);
    }
    this.closeFrame(invocationId, text, opts);
  }

  private closeFrame(invocationId: string, text: string, opts: SubagentResultOpts): void {
    const frame = this.frames.get(invocationId)!;
    this.frames.delete(invocationId);
    this.emitOrBuffer(
      this.nowEvent("subagent_returned", frame.spanId, frame.parentSpanId, {
        "avp.step": frame.step,
        "avp.subagent.name": frame.name,
        "avp.subagent.invocation_id": invocationId,
        "avp.duration_ms": this.elapsedMs(frame.startedAt),
        "avp.subagent.result.text": text,
        "avp.subagent.result.structured": opts.structured,
        "avp.subagent.reason": opts.reason ?? "converged",
        "avp.subagent.usage": opts.usage,
      }),
    );
  }
}

function isResultBlock(content: unknown): content is ToolResultBlock {
  return (
    typeof content === "object" &&
    content !== null &&
    !Array.isArray(content) &&
    (content as Block).type === "tool_result"
  );
}

/**
 * A server tool's inline result (provider-shaped, not AVP blocks) as
 * `ToolResultBlock.content`: strings pass through, anything else is
 * JSON-encoded the way Python's `json.dumps` does.
 */
function resultContent(content: unknown): string {
  if (content === null || content === undefined) return "";
  if (typeof content === "string") return content;
  return pythonJson(content);
}

/** `json.dumps` default separators (`", "` and `": "`), so every binding encodes the same payload to the same string. */
function pythonJson(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(pythonJson).join(", ")}]`;
  if (v !== null && typeof v === "object") {
    return `{${Object.entries(v)
      .map(([k, x]) => `${JSON.stringify(k)}: ${pythonJson(x)}`)
      .join(", ")}}`;
  }
  return JSON.stringify(v) ?? "null";
}
