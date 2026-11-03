import { randomUUID } from "node:crypto";
import {
  parseCommission,
  type Commission,
  type ModelRef,
} from "./commission.js";
import { parseDescriptor, type AgentDescriptor } from "./descriptor.js";
import {
  parseTrajectoryEvent,
  type AgentStarted,
  type ContentBlock,
  type ErrorCode,
  type Event,
  type EventSink,
  type JsonValue,
  type StopReason,
  type SubagentUsage,
  type ToolResultBlock,
  type Usage,
} from "./trajectory.js";
import { parseDefinition } from "./validation.js";
import { checkCommission } from "./utils/preflight.js";
import { computeCost, loadPrices, type Prices } from "./utils/pricing.js";
import { repr } from "./utils/skill_md.js";

export const ABANDONED_TEXT =
  "The run ended while the subagent was still running.";
export const UNRETURNED_TEXT = "The run ended before the tool returned.";
export const STOPPED_BEFORE_START_TEXT =
  "The run stopped before agent_started.";
export class RecorderError extends Error {}
export type UsageReport = Omit<Usage, "cost_source" | "cost_usd"> & {
  cost_usd?: number | null;
};
export interface RecorderOptions {
  runId?: string;
  prices?: Prices;
  now?: () => Date;
  newId?: () => string;
}
export interface ResponseOptions {
  usage?: UsageReport | null;
  model?: ModelRef | null;
  responseModel?: string | null;
  finishReasons?: string[] | null;
  durationMs?: number | null;
  subagentInvocationId?: string | null;
  key?: string | null;
  meta?: Record<string, JsonValue> | null;
}
interface Call {
  name: string;
  input: Record<string, JsonValue>;
  parent?: string;
  time: number;
  returned: boolean;
}
interface Subagent {
  name: string;
  parent?: string;
  time: number;
  reason?: StopReason;
}
interface Response {
  key?: string;
  model: ModelRef;
  parent?: string;
  opened: number;
  last: number;
  content: ContentBlock[];
  usage?: UsageReport;
  responseModel?: string;
  finishReasons?: string[];
  durationMs?: number;
  meta: Record<string, JsonValue>;
  callIds: Set<string>;
  waiting: Event[];
  toolReturned: boolean;
}
function usageReport(report: UsageReport): UsageReport {
  if (Object.hasOwn(report, "cost_source"))
    throw new TypeError("UsageReport has no cost_source field");
  const {
    cost_source: _source,
    cost_usd: _cost,
    ...counts
  } = parseDefinition<Usage>("Usage", {
    ...report,
    cost_usd: report.cost_usd ?? 0,
    cost_source: "unknown",
  });
  if (
    (report.cache_read_input_tokens ?? 0) +
      (report.cache_creation_input_tokens ?? 0) >
    report.input_tokens
  )
    throw new RangeError("cache read and creation tokens exceed input_tokens");
  return {
    ...counts,
    ...(report.cost_usd == null ? {} : { cost_usd: report.cost_usd }),
  };
}

export class Recorder {
  runId: string;
  ended = false;
  private begun = false;
  private started?: AgentStarted;
  private openResponse?: Response;
  private calls = new Map<string, Call>();
  private subagents = new Map<string, Subagent>();
  private reportedResponses = new Set<string>();
  private prices?: Prices;
  private now: () => Date;
  private newId: () => string;

  constructor(
    private sink: EventSink,
    options: RecorderOptions = {},
  ) {
    this.newId = options.newId ?? randomUUID;
    this.now = options.now ?? (() => new Date());
    this.runId = options.runId || this.newId();
    this.prices = options.prices;
  }
  private check(report: string, started = true): void {
    if (this.ended) throw new RecorderError(`${report}: the run has ended`);
    if (started && !this.started)
      throw new RecorderError(`${report}: called before start`);
  }
  private event<K extends Event["type"]>(
    type: K,
    data: Extract<Event, { type: K }>["data"],
    time?: number,
    meta?: Record<string, JsonValue> | null,
  ): Event {
    return parseTrajectoryEvent({
      avp_version: "0.1",
      id: this.newId(),
      time:
        time === undefined
          ? this.now().toISOString()
          : new Date(time).toISOString(),
      run_id: this.runId,
      type,
      data,
      meta,
    })!;
  }
  private async write(event: Event): Promise<void> {
    if (this.openResponse) this.openResponse.waiting.push(event);
    else await this.sink(event);
  }

  async begin(
    received: JsonValue,
    descriptor: AgentDescriptor,
  ): Promise<Commission | undefined> {
    this.check("begin", false);
    if (this.begun || this.started)
      throw new RecorderError("begin: called twice, or after start");
    this.begun = true;
    descriptor = parseDescriptor(descriptor);
    let commission: Commission | undefined;
    let refusal: string | undefined;
    if (received != null) {
      try {
        commission = parseCommission(received);
      } catch (error) {
        refusal = `the Commission doesn't match the spec: ${(error as Error).message}`;
      }
      if (
        typeof received === "object" &&
        "run_id" in received &&
        typeof received.run_id === "string"
      )
        this.runId = received.run_id;
    }
    await this.sink(this.event("run_requested", { commission: received }));
    await this.sink(this.event("agent_described", { descriptor }));
    if (commission) refusal = checkCommission(commission, descriptor);
    if (refusal) {
      await this.error("invalid_commission", refusal);
      return;
    }
    return commission;
  }
  async start(
    started: AgentStarted,
    { meta }: { meta?: Record<string, JsonValue> | null } = {},
  ): Promise<void> {
    this.check("start", false);
    if (this.started) throw new RecorderError("start: called twice");
    this.started = parseDefinition<AgentStarted>("AgentStarted", started);
    await this.sink(this.event("agent_started", this.started, undefined, meta));
  }
  async error(
    code: ErrorCode,
    message: string,
    { subagentInvocationId }: { subagentInvocationId?: string } = {},
  ): Promise<void> {
    this.check("error", false);
    const event = this.event("error_occurred", {
      error_code: code,
      error_message: message,
      subagent_invocation_id: subagentInvocationId,
    });
    if (!this.started) {
      this.ended = true;
      await this.sink(event);
    } else await this.write(event);
  }
  async stop(reason: StopReason, output?: JsonValue): Promise<void> {
    if (this.ended) return;
    if (!this.started) {
      await this.error("agent_crash", STOPPED_BEFORE_START_TEXT);
      return;
    }
    await this.closeResponse();
    const running = [...this.subagents]
      .filter(([, subagent]) => subagent.reason === undefined)
      .map(([id]) => id);
    for (const id of running)
      await this.subagentReturned(id, ABANDONED_TEXT, "abandoned");
    for (const [id, call] of this.calls)
      if (!call.returned)
        await this.toolReturned(id, UNRETURNED_TEXT, { isError: true });
    if (running.length && reason === "converged") reason = "abandoned";
    this.ended = true;
    await this.sink(this.event("agent_stopped", { reason, output }));
  }

  async response(
    content: ContentBlock[],
    options: ResponseOptions = {},
  ): Promise<void> {
    this.check("response");
    const usage =
      options.usage == null ? undefined : usageReport(options.usage);
    const calls = content.filter((block) => block.type === "tool_use");
    const ids = new Set<string>();
    for (const call of calls) {
      if (this.calls.has(call.id) || ids.has(call.id))
        throw new RecorderError(
          `response: tool_use id ${repr(call.id)} was already used`,
        );
      ids.add(call.id);
    }
    const key = options.key ?? undefined;
    const parent = options.subagentInvocationId ?? undefined;
    const open = this.openResponse;
    if (
      open &&
      (key === undefined ||
        key !== open.key ||
        open.toolReturned ||
        parent !== open.parent)
    )
      await this.closeResponse();
    const now = this.now().getTime();
    const response = (this.openResponse ??= {
      key,
      model: options.model ?? this.started!.model,
      parent,
      opened: now,
      last: now,
      content: [],
      meta: {},
      callIds: new Set(),
      waiting: [],
      toolReturned: false,
    });
    response.last = now;
    response.content.push(...content);
    if (usage) response.usage = usage;
    if (response.responseModel === undefined)
      response.responseModel = options.responseModel ?? undefined;
    if (options.finishReasons != null)
      response.finishReasons = options.finishReasons;
    if (options.durationMs != null) response.durationMs = options.durationMs;
    if (options.meta) Object.assign(response.meta, options.meta);
    if (parent !== undefined) this.reportedResponses.add(parent);
    const servers = new Map(
      (this.started!.tools ?? []).map((tool) => [
        tool.name,
        tool.mcp_server_id,
      ]),
    );
    for (const call of calls) {
      this.calls.set(call.id, {
        name: call.name,
        input: call.input,
        parent,
        time: now,
        returned: false,
      });
      response.callIds.add(call.id);
      response.waiting.push(
        this.event("tool_invoked", {
          tool_call_id: call.id,
          tool_name: call.name,
          tool_input: call.input,
          mcp_server_id: servers.get(call.name),
          subagent_invocation_id: parent,
        }),
      );
    }
    if (key === undefined) await this.closeResponse();
  }
  async usage(
    report: UsageReport,
    { key }: { key?: string | null } = {},
  ): Promise<void> {
    this.check("usage");
    const response = this.openResponse;
    if (!response || (key != null && key !== response.key))
      throw new RecorderError(
        `usage: no open response with key ${key == null ? "None" : repr(key)}`,
      );
    response.usage = usageReport(report);
  }
  async closeResponse(): Promise<void> {
    const response = this.openResponse;
    if (!response) return;
    this.openResponse = undefined;
    if (
      response.content.some(
        (block) => block.type !== "text" || block.text !== "",
      )
    ) {
      let usage: Usage = {
        input_tokens: 0,
        output_tokens: 0,
        cost_usd: 0,
        cost_source: "unknown",
      };
      const report = response.usage;
      if (report) {
        if (!this.prices && report.cost_usd == null)
          this.prices = await loadPrices();
        const [cost, source] = computeCost(
          this.prices ?? {
            source: "https://models.dev/api.json",
            fetched: this.now().toISOString(),
            models: {},
          },
          response.model,
          {
            inputTokens: report.input_tokens,
            outputTokens: report.output_tokens,
            cacheReadInputTokens: report.cache_read_input_tokens ?? 0,
            cacheCreationInputTokens: report.cache_creation_input_tokens ?? 0,
            responseModel: response.responseModel,
            reportedCostUsd: report.cost_usd,
          },
        );
        usage = { ...report, cost_usd: cost, cost_source: source };
      }
      await this.sink(
        this.event(
          "assistant_message",
          {
            content: response.content,
            model: response.model,
            response_model: response.responseModel,
            finish_reasons: response.finishReasons,
            duration_ms:
              response.durationMs ??
              Math.max(0, response.last - response.opened),
            usage,
            subagent_invocation_id: response.parent,
          },
          response.last,
          Object.keys(response.meta).length ? response.meta : undefined,
        ),
      );
    }
    for (const event of response.waiting) await this.sink(event);
  }

  async toolReturned(
    id: string,
    content: ToolResultBlock["content"],
    {
      isError,
      structuredContent,
    }: {
      isError?: boolean | null;
      structuredContent?: ToolResultBlock["structured_content"];
    } = {},
  ): Promise<void> {
    this.check("tool_returned");
    const call = this.calls.get(id);
    if (!call || call.returned)
      throw new RecorderError(
        `tool_returned: tool call ${repr(id)} is ${call ? "already returned" : "unknown"}`,
      );
    call.returned = true;
    const subagent = this.subagents.get(id);
    if (subagent?.reason !== undefined)
      isError = subagent.reason !== "converged";
    if (this.openResponse?.callIds.has(id))
      this.openResponse.toolReturned = true;
    await this.write(
      this.event("tool_returned", {
        tool_call_id: id,
        tool_name: call.name,
        duration_ms: Math.max(0, this.now().getTime() - call.time),
        subagent_invocation_id: call.parent,
        tool_result: {
          type: "tool_result",
          tool_use_id: id,
          content,
          structured_content: structuredContent,
          is_error: isError,
        },
      }),
    );
  }
  async subagentInvoked(
    id: string,
    name: string,
    input?: Record<string, JsonValue> | null,
    { subagentInvocationId }: { subagentInvocationId?: string } = {},
  ): Promise<void> {
    this.check("subagent_invoked");
    if (this.subagents.has(id))
      throw new RecorderError(`subagent_invoked: ${repr(id)} was already used`);
    const call = this.calls.get(id);
    if (call) {
      input ??= call.input;
      subagentInvocationId ||= call.parent;
    }
    this.subagents.set(id, {
      name,
      parent: subagentInvocationId,
      time: this.now().getTime(),
    });
    await this.write(
      this.event("subagent_invoked", {
        subagent_name: name,
        invocation_id: id,
        subagent_input: input ?? {},
        subagent_invocation_id: subagentInvocationId,
      }),
    );
  }
  async subagentReturned(
    id: string,
    text: string,
    reason: StopReason = "converged",
    { usage }: { usage?: SubagentUsage | null } = {},
  ): Promise<void> {
    this.check("subagent_returned");
    const subagent = this.subagents.get(id);
    if (!subagent || subagent.reason !== undefined)
      throw new RecorderError(
        `subagent_returned: subagent ${repr(id)} is ${subagent ? "already returned" : "unknown"}`,
      );
    subagent.reason = reason;
    if (this.reportedResponses.has(id)) usage = undefined;
    await this.write(
      this.event("subagent_returned", {
        subagent_name: subagent.name,
        invocation_id: id,
        subagent_invocation_id: subagent.parent,
        duration_ms: Math.max(0, this.now().getTime() - subagent.time),
        subagent_reason: reason,
        subagent_result_text: text,
        subagent_usage: usage,
      }),
    );
  }
}
