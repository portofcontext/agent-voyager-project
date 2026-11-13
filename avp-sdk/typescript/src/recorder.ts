import { randomUUID } from "node:crypto";
import { ArtifactCollection } from "./_artifacts.js";
import type { Role } from "./artifacts.js";
import {
  parseCommission,
  type Commission,
  type ModelRef,
} from "./commission.js";
import { parseDescriptor, type AgentDescriptor } from "./descriptor.js";
import {
  type RunContext,
  type ContentBlock,
  type ErrorCode,
  type JsonValue,
  type StopReason,
  type SubagentUsage,
  type ToolResultBlock,
  type Usage,
} from "./reports.js";
import { parseDefinition } from "./validation.js";
import { checkCommission } from "./utils/preflight.js";
import { computeCost, loadPrices, type Prices } from "./utils/pricing.js";
import { repr } from "./utils/skill_md.js";

export const ABANDONED_TEXT =
  "The run ended while the subagent was still running.";
export const UNRETURNED_TEXT = "The run ended before the tool returned.";
export const STOPPED_BEFORE_START_TEXT = "The run stopped before start.";
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
  step?: any;
  server?: string;
}
interface Subagent {
  name: string;
  parent?: string;
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
  waiting: (() => void)[];
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

import { parseTrajectory, type TrajectorySink } from "./trajectory.js";
import {
  Document,
  metadata,
  remaining,
  content,
  contentMetadata,
  metrics,
  observation,
} from "./_recording.js";
export class Recorder {
  runId: string;
  ended = false;
  private begun = false;
  private started?: RunContext;
  private openResponse?: Response;
  private calls = new Map<string, Call>();
  private subagents = new Map<string, Subagent>();
  private prices?: Prices;
  private now: () => Date;
  private root: Document;
  private docs: Map<string | undefined, Document>;
  private delegations = new Map<string, any>();
  private assets = new Map<string, Uint8Array>();
  private artifacts = new ArtifactCollection();
  constructor(
    private sink: TrajectorySink,
    options: RecorderOptions = {},
  ) {
    this.runId = options.runId || (options.newId ?? randomUUID)();
    this.now = options.now ?? (() => new Date());
    this.prices = options.prices;
    this.root = new Document(
      this.runId,
      `${this.runId}/root`,
      "unknown",
      "unknown",
    );
    this.docs = new Map([[undefined, this.root]]);
  }
  private check(report: string, started = true): void {
    if (this.ended) throw new RecorderError(`${report}: the run has ended`);
    if (started && !this.started)
      throw new RecorderError(`${report}: called before start`);
  }
  private scope(id?: string): Document {
    const doc = this.docs.get(id);
    if (!doc) throw new RecorderError(`unknown subagent ${id}`);
    return doc;
  }
  private async publish(): Promise<void> {
    this.root.finish();
    await this.sink({
      trajectory: parseTrajectory(this.root.data),
      artifacts: new Map(this.artifacts.files),
      assets: new Map(this.assets),
    });
  }
  async artifact(path: string, content: Uint8Array, role: Role): Promise<void> {
    this.check("artifact", false);
    this.artifacts.add(path, content, role);
    await this.publish();
  }
  private async write(update: () => void): Promise<void> {
    if (this.openResponse) this.openResponse.waiting.push(update);
    else {
      update();
      await this.publish();
    }
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
    let commission: Commission | undefined, refusal: string | undefined;
    if (received != null) {
      try {
        commission = parseCommission(received);
      } catch (e) {
        refusal = `the Commission doesn't match the spec: ${(e as Error).message}`;
      }
      if (
        typeof received === "object" &&
        "run_id" in received &&
        typeof received.run_id === "string"
      )
        this.runId = received.run_id;
    }
    this.root = new Document(
      this.runId,
      `${this.runId}/root`,
      descriptor.agent_name,
      descriptor.agent_version,
    );
    this.docs = new Map([[undefined, this.root]]);
    this.artifacts.begin(commission, descriptor);
    this.root.step(this.now().toISOString(), "system", "Run initialized.");
    if (commission) refusal = checkCommission(commission, descriptor);
    if (refusal) {
      await this.error("invalid_commission", refusal);
      return;
    }
    await this.publish();
    return commission;
  }
  async start(
    started: RunContext,
    { meta }: { meta?: Record<string, JsonValue> | null } = {},
  ): Promise<void> {
    this.check("start", false);
    if (this.started) throw new RecorderError("start: called twice");
    const data = parseDefinition<RunContext>("RunContext", started);
    this.artifacts.effective(data);
    this.started = data;
    this.root.data.steps = [];
    metadata(this.root.data).started_at = this.now().toISOString();
    if (meta) metadata(this.root.data).annotations = structuredClone(meta);
    const agent = this.root.data.agent;
    agent.model_name = data.model.id;
    agent.extra = { avp: { provider: data.model.provider } };
    agent.tool_definitions = (data.tools ?? []).map((t) => ({
      type: "function",
      function: {
        name: t.name,
        parameters: t.inputSchema,
        ...(t.description != null ? { description: t.description } : {}),
      },
      ...(Object.keys(remaining(t, ["name", "description", "inputSchema"]))
        .length
        ? {
            extra: {
              avp: remaining(t, ["name", "description", "inputSchema"]),
            },
          }
        : {}),
    }));
    if (data.system_prompt != null)
      this.root.step(this.now().toISOString(), "system", data.system_prompt);
    this.root.step(this.now().toISOString(), "user", data.prompt);
    await this.publish();
  }
  async error(
    code: ErrorCode,
    message: string,
    { subagentInvocationId }: { subagentInvocationId?: string } = {},
  ): Promise<void> {
    this.check("error", false);
    const timestamp = this.now().toISOString();
    await this.write(() => {
      const doc = this.scope(subagentInvocationId);
      if (!this.started) {
        doc.data.steps = [];
        this.ended = true;
        Object.assign(metadata(doc.data), {
          complete: true,
          stop_reason: "error",
          stopped_at: timestamp,
        });
      }
      metadata(doc.step(timestamp, "system", message)).error_code = code;
    });
  }
  async stop(reason: StopReason, output?: JsonValue): Promise<void> {
    if (this.ended) return;
    if (!this.started) {
      await this.error("agent_crash", STOPPED_BEFORE_START_TEXT);
      return;
    }
    await this.closeResponse();
    const running = [...this.subagents]
      .filter(([, s]) => !s.reason)
      .map(([id]) => id);
    for (const id of running)
      await this.subagentReturned(id, ABANDONED_TEXT, "abandoned");
    for (const [id, call] of this.calls)
      if (!call.returned)
        await this.toolReturned(id, UNRETURNED_TEXT, { isError: true });
    if (running.length && reason === "converged") reason = "abandoned";
    this.ended = true;
    Object.assign(metadata(this.root.data), {
      complete: true,
      stop_reason: reason,
      stopped_at: this.now().toISOString(),
    });
    const lastMessage = this.root.data.steps.findLast(
      (step: any) => step.source === "agent",
    )?.message;
    if (
      !(typeof output === "string" && output === lastMessage) &&
      (output != null || lastMessage != null)
    ) {
      metadata(this.root.data).output = output ?? null;
    }
    await this.publish();
  }
  async response(
    blocks: ContentBlock[],
    options: ResponseOptions = {},
  ): Promise<void> {
    this.check("response");
    const usage =
      options.usage == null ? undefined : usageReport(options.usage);
    const calls = blocks.filter((b) => b.type === "tool_use"),
      ids = new Set<string>();
    for (const call of calls) {
      if (this.calls.has(call.id) || ids.has(call.id))
        throw new RecorderError(
          `response: tool_use id ${repr(call.id)} was already used`,
        );
      ids.add(call.id);
    }
    const key = options.key ?? undefined,
      parent = options.subagentInvocationId ?? undefined,
      open = this.openResponse;
    if (
      open &&
      (key === undefined ||
        key !== open.key ||
        open.toolReturned ||
        parent !== open.parent)
    )
      await this.closeResponse();
    this.scope(parent);
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
    response.content.push(...blocks);
    if (usage) response.usage = usage;
    response.responseModel ??= options.responseModel ?? undefined;
    if (options.finishReasons != null)
      response.finishReasons = options.finishReasons;
    if (options.durationMs != null) response.durationMs = options.durationMs;
    if (options.meta) Object.assign(response.meta, options.meta);
    for (const call of calls) {
      this.calls.set(call.id, {
        name: call.name,
        input: call.input,
        parent,
        time: now,
        returned: false,
        server:
          this.started!.tools?.find((t) => t.name === call.name)
            ?.mcp_server_id ?? undefined,
      });
      response.callIds.add(call.id);
    }
    if (key === undefined) await this.closeResponse();
  }
  async usage(
    report: UsageReport,
    { key }: { key?: string | null } = {},
  ): Promise<void> {
    this.check("usage");
    if (!this.openResponse || (key != null && key !== this.openResponse.key))
      throw new RecorderError(`usage: no open response with key ${key}`);
    this.openResponse.usage = usageReport(report);
  }
  async closeResponse(): Promise<void> {
    const response = this.openResponse;
    if (!response) return;
    this.openResponse = undefined;
    if (response.content.some((b) => b.type !== "text" || b.text !== ""))
      await this.recordResponse(response);
    for (const update of response.waiting) update();
    await this.publish();
  }
  private async recordResponse(response: Response): Promise<void> {
    const report = response.usage;
    let usage: any = {};
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
    const doc = this.scope(response.parent),
      blocks = response.content as any[],
      visible = blocks.filter((b) =>
        ["text", "image", "refusal"].includes(b.type),
      );
    const step = doc.step(
      new Date(response.last).toISOString(),
      "agent",
      content(visible, this.assets),
    );
    Object.assign(step, {
      llm_call_count: 1,
      metrics: metrics(usage),
    });
    doc.recordModel(
      step,
      response.model,
      response.responseModel ?? response.model.id,
    );
    const meta = metadata(step);
    Object.assign(meta, {
      duration_ms:
        response.durationMs ?? Math.max(0, response.last - response.opened),
    });
    if (response.finishReasons?.length)
      meta.finish_reasons = response.finishReasons;
    if (Object.keys(response.meta).length) meta.annotations = response.meta;
    const annotations = contentMetadata(visible);
    if (annotations.length) meta.message_metadata = annotations;
    const reasoning = blocks
      .filter((b) => b.type === "thinking" && !b.redacted)
      .map((b) => b.thinking);
    if (reasoning.length) step.reasoning_content = reasoning.join("\n");
    const details: any[] = [];
    let offset = 0;
    for (const b of blocks.filter((b) => b.type === "thinking")) {
      const entry = remaining(b, ["type", "thinking"]);
      if (b.redacted) entry.encrypted_content = b.thinking;
      else if (Object.keys(entry).length)
        Object.assign(entry, {
          start: offset,
          end: offset + b.thinking.length,
        });
      if (!b.redacted) offset += b.thinking.length + 1;
      if (Object.keys(entry).length) details.push(entry);
    }
    if (details.length) meta.reasoning_metadata = details;
    for (const block of blocks) {
      if (!["tool_use", "server_tool_use"].includes(block.type)) continue;
      const call = {
        tool_call_id: block.id,
        function_name: block.name,
        arguments: block.input,
      };
      if (block.type === "server_tool_use") metadata(call).server_side = true;
      const extra = remaining(block, ["type", "id", "name", "input"]);
      if (Object.keys(extra).length) metadata(call).provider_metadata = extra;
      if (block.type === "tool_use") {
        const state = this.calls.get(block.id)!;
        state.step = step;
        metadata(call).started_at = new Date(state.time).toISOString();
        const declaredServer = doc.data.agent.tool_definitions?.find(
          (t: any) => t.function.name === block.name,
        )?.extra?.avp?.mcp_server_id;
        if (state.server && state.server !== declaredServer)
          metadata(call).mcp_server_id = state.server;
      }
      (step.tool_calls ??= []).push(call);
    }
    for (const block of blocks)
      if (["tool_result", "server_tool_result"].includes(block.type))
        this.result(
          step,
          block.tool_use_id,
          block.content,
          new Date(response.last).toISOString(),
          block.is_error,
          {
            provider_metadata: remaining(block, [
              "type",
              "tool_use_id",
              "name",
              "content",
              "is_error",
            ]),
          },
        );
    doc.usages.push(usage);
  }
  private result(
    step: any,
    id: string,
    raw: any,
    time: string,
    isError?: boolean | null,
    details: any = {},
  ): void {
    if (!step.tool_calls?.some((c: any) => c.tool_call_id === id))
      throw new RecorderError(`unmatched tool result ${id}`);
    const result = observation(step, id);
    Object.assign(result, {
      content: content(raw, this.assets),
      extra: {
        avp: {
          finished_at: time,
          is_error: !!isError,
          ...Object.fromEntries(
            Object.entries(details).filter(
              ([, v]) => v != null && JSON.stringify(v) !== "{}",
            ),
          ),
        },
      },
    });
    const annotations = contentMetadata(raw);
    if (annotations.length) metadata(result).content_metadata = annotations;
  }
  async toolReturned(
    id: string,
    raw: ToolResultBlock["content"],
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
    const child = this.subagents.get(id);
    if (child?.reason) isError = child.reason !== "converged";
    if (this.openResponse?.callIds.has(id))
      this.openResponse.toolReturned = true;
    const time = this.now().toISOString();
    await this.write(() => {
      if (!call.step) throw new RecorderError(`tool ${id} has no response`);
      this.result(call.step, id, raw, time, isError, {
        structured_content: structuredContent,
      });
    });
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
    });
    const time = this.now().toISOString();
    await this.write(() => {
      const parent = this.scope(subagentInvocationId),
        child = new Document(
          this.runId,
          `${this.runId}/subagent/${id}`,
          name,
          "unknown",
        );
      this.docs.set(id, child);
      parent.children.push(child);
      (parent.data.subagent_trajectories ??= []).push(child.data);
      metadata(child.data).started_at = time;
      child.step(time, "user", JSON.stringify(input ?? {}));
      const result = call?.step
        ? observation(call.step, id)
        : observation(parent.step(time, "system", `Delegated to ${name}.`));
      result.subagent_trajectory_ref = [
        { trajectory_id: child.data.trajectory_id },
      ];
      this.delegations.set(id, result);
    });
  }
  async subagentReturned(
    id: string,
    text: string,
    reason: StopReason = "converged",
    { usage }: { usage?: SubagentUsage | null } = {},
  ): Promise<void> {
    this.check("subagent_returned");
    const child = this.subagents.get(id);
    if (!child || child.reason)
      throw new RecorderError(
        `subagent_returned: subagent ${repr(id)} is ${child ? "already returned" : "unknown"}`,
      );
    child.reason = reason;
    const time = this.now().toISOString();
    await this.write(() => {
      const doc = this.scope(id);
      Object.assign(metadata(doc.data), {
        complete: true,
        stop_reason: reason,
        stopped_at: time,
      });
      const result = this.delegations.get(id);
      result.content ??= text;
      if (!doc.usages.length) {
        const counts = usage ?? {};
        doc.usages.push(counts);
        const details = metrics(counts).extra?.avp;
        if (details && Object.keys(details).length)
          metadata(doc.data).usage_details = details;
      }
    });
  }
}
