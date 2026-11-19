/** Builds a run's ATIF Trajectory and writes it once when the run ends. */
import { createHash, randomUUID } from "node:crypto";
import { readFileSync, readdirSync, lstatSync, realpathSync } from "node:fs";
import { join, resolve } from "node:path";
import { parseCommission, type Commission } from "./commission.js";
import type { AgentDescriptor } from "./descriptor.js";
import {
  parseTrajectory,
  type Agent,
  type TrajectorySink,
  type StopReason,
  type ErrorCode,
  type Metrics,
} from "./trajectory.js";
import type {
  Text,
  Image,
  Reasoning,
  Call,
  ServerResult,
  Usage,
  JsonValue,
} from "./wire.js";
import { checkCommission } from "./utils/preflight.js";
import { computeCost, loadPrices, type Prices } from "./utils/pricing.js";
export type {
  Text,
  Image,
  Reasoning,
  Call,
  ServerResult,
  Usage,
  JsonValue,
} from "./wire.js";
export type Part = Text | Image | Reasoning | Call | ServerResult;
export class RecorderError extends Error {}
export interface RecorderOptions {
  runId?: string;
  prices?: Prices;
  now?: () => Date;
  newId?: () => string;
}
const UNRETURNED_TEXT = "The run ended before the tool returned.";
const TOTALS: [string, string, boolean][] = [
  ["prompt_tokens", "total_prompt_tokens", false],
  ["completion_tokens", "total_completion_tokens", false],
  ["cached_tokens", "total_cached_tokens", false],
  ["cache_creation_input_tokens", "total_cache_creation_input_tokens", true],
  ["reasoning_output_tokens", "total_reasoning_output_tokens", true],
];
function avp(value: any): any {
  return ((value.extra ??= {}).avp ??= {});
}
function get(value: any, key: string, extra: boolean): any {
  return (extra ? (value.extra?.avp ?? {}) : value)[key];
}
function ms(start: Date, end: Date): number {
  return Math.max(0, Math.round(end.getTime() - start.getTime()));
}
function metrics(usage: Usage): any {
  const { cache_creation_input_tokens, reasoning_output_tokens, ...data } =
    usage;
  for (const [key, value] of Object.entries({
    cache_creation_input_tokens,
    reasoning_output_tokens,
  }))
    if (value != null) avp(data)[key] = value;
  return Object.fromEntries(Object.entries(data).filter(([, v]) => v != null));
}
function totals(metrics: any): any {
  const result: any = {};
  for (const [key, total, extra] of TOTALS) {
    const value = get(metrics, key, extra);
    if (value != null) (extra ? avp(result) : result)[total] = value;
  }
  if (metrics.cost_usd != null) result.total_cost_usd = metrics.cost_usd;
  return result;
}
class Document {
  provider?: string;
  last?: Date;
  children: Document[] = [];
  reported?: any;
  stopReason?: StopReason;
  constructor(public data: any) {}
  step(timestamp: Date, source: string, message: any): any {
    const step = {
      step_id: this.data.steps.length + 1,
      timestamp: timestamp.toISOString(),
      source,
      message,
    };
    this.data.steps.push(step);
    return step;
  }
  stopped(reason: StopReason, timestamp: Date): void {
    this.stopReason = reason;
    Object.assign(avp(this.data), {
      stop_reason: reason,
      stopped_at: timestamp.toISOString(),
    });
  }
  final(): any {
    const children = this.children.map((c) => c.final());
    const own = this.data.steps
      .filter((s: any) => s.source === "agent")
      .map((s: any) => s.metrics ?? {});
    const result: any = { total_steps: this.data.steps.length };
    if (this.reported != null && !own.length) {
      Object.assign(result, this.reported);
      this.data.final_metrics = result;
      return result;
    }
    const counted = children.filter(
      (c) => get(c, "total_responses", true) !== 0,
    );
    const responses = counted.map((c) => get(c, "total_responses", true));
    for (const [key, total, extra] of TOTALS) {
      const values = [
        ...own.map((m: any) => get(m, key, extra)),
        ...counted.map((c) => get(c, total, extra)),
      ];
      if (values.length && values.every((v) => v != null))
        (extra ? avp(result) : result)[total] = values.reduce(
          (a, b) => a + b,
          0,
        );
    }
    const costs = [
      ...own.map((m: any) => m.cost_usd),
      ...counted.map((c) => c.total_cost_usd),
    ];
    const known = costs.filter((c) => c != null);
    if (known.length) {
      result.total_cost_usd = known.reduce((a, b) => a + b, 0);
      if (
        known.length < costs.length ||
        counted.some((c) => get(c, "cost_complete", true) === false)
      )
        avp(result).cost_complete = false;
    }
    if (responses.every((r) => r != null))
      avp(result).total_responses =
        own.length + responses.reduce((a, b) => a + b, 0);
    this.data.final_metrics = result;
    return result;
  }
}
interface ToolCall {
  document: Document;
  step: any;
  time: Date;
  returned: boolean;
}
export class Recorder {
  runId: string;
  ended = false;
  private begun = false;
  private started = false;
  private root: Document;
  private subagents = new Map<string, Document>();
  private calls = new Map<string, ToolCall>();
  private assets = new Map<string, Uint8Array>();
  private commission?: Commission;
  private prices?: Prices;
  private now: () => Date;
  constructor(
    private sink: TrajectorySink,
    options: RecorderOptions = {},
  ) {
    this.runId = options.runId || (options.newId ?? randomUUID)();
    this.prices = options.prices;
    this.now = options.now ?? (() => new Date());
    this.root = this.document(this.runId, "unknown", "unknown");
  }
  private document(id: string, name: string, version: string): Document {
    return new Document({
      schema_version: "ATIF-v1.8",
      session_id: this.runId,
      trajectory_id: id,
      agent: { name, version },
      steps: [],
      extra: { avp: { avp_version: "0.1" } },
    });
  }
  private check(report: string, started = true): void {
    if (this.ended) throw new RecorderError(`${report}: the run has ended`);
    if (started && !this.started)
      throw new RecorderError(`${report}: called before start`);
  }
  private scope(subagent?: string | null): Document {
    if (subagent == null) return this.root;
    const doc = this.subagents.get(subagent);
    if (!doc) throw new RecorderError(`unknown subagent ${subagent}`);
    if (doc.stopReason != null)
      throw new RecorderError(`subagent ${subagent} has stopped`);
    return doc;
  }
  private async write(): Promise<void> {
    this.root.final();
    await this.sink({
      trajectory: parseTrajectory(this.root.data),
      assets: new Map(this.assets),
    });
  }
  async begin(
    received: JsonValue,
    descriptor: AgentDescriptor,
  ): Promise<Commission | undefined> {
    this.check("begin", false);
    if (this.begun) throw new RecorderError("begin: called twice");
    this.begun = true;
    if (
      received &&
      typeof received === "object" &&
      "run_id" in received &&
      typeof received.run_id === "string"
    )
      this.runId = received.run_id;
    this.root = this.document(
      this.runId,
      descriptor.agent_name,
      descriptor.agent_version,
    );
    avp(this.root.data.agent).descriptor = structuredClone(descriptor);
    if (received == null) return;
    avp(this.root.data).commission = structuredClone(received);
    let commission: Commission;
    try {
      commission = parseCommission(received);
    } catch (error) {
      await this.error(
        "invalid_commission",
        `the Commission doesn't match the spec: ${error}`,
      );
      return;
    }
    const refusal = checkCommission(commission, descriptor);
    if (refusal != null) {
      await this.error("invalid_commission", refusal);
      return;
    }
    this.commission = commission;
    return commission;
  }
  async start(
    agent: Agent,
    prompt: string,
    options: { systemPrompt?: string | null } = {},
  ): Promise<void> {
    this.check("start", false);
    if (this.started) throw new RecorderError("start: called twice");
    const given = JSON.parse(JSON.stringify(agent));
    const extra = given.extra?.avp ?? {};
    if (!extra.model)
      throw new RecorderError("start: agent.extra.avp.model is required");
    this.captureSkills(extra);
    this.root.data.agent = {
      ...given,
      name: this.root.data.agent.name,
      version: this.root.data.agent.version,
      extra: {
        ...given.extra,
        avp: { ...extra, ...this.root.data.agent.extra?.avp },
      },
    };
    this.root.provider = extra.model.provider;
    this.started = true;
    const now = this.now();
    this.root.last = now;
    avp(this.root.data).started_at = now.toISOString();
    if (options.systemPrompt != null)
      this.root.step(now, "system", options.systemPrompt);
    this.root.step(now, "user", prompt);
  }
  private captureSkills(extra: any): void {
    const supplied = new Map(
      (this.commission?.skills ?? []).map((s) => [s.name, s.files]),
    );
    const scopes: [string, any[]][] = [
      ["skills", extra.skills ?? []],
      ...(extra.subagents ?? []).map(
        (c: any, i: number) =>
          [`skills/subagent-${i}`, c.skills ?? []] as [string, any[]],
      ),
    ];
    for (const [prefix, skills] of scopes)
      for (const [index, skill] of skills.entries()) {
        const files = this.skillFiles(
          skill,
          prefix === "skills" ? (supplied.get(skill.name) ?? {}) : {},
        );
        if (!files.size) {
          delete skill.source;
          continue;
        }
        const directory = `${prefix}/${index}-${skill.name.replace(/[^A-Za-z0-9._-]/g, "-")}`;
        for (const [path, content] of files) {
          if (
            !/^(?!\/)(?!.*(?:^|\/)\.\.?(?:\/|$))(?!.*\/\/)(?!.*\/$)[^\\:\x00-\x1f]+$/.test(
              path,
            )
          )
            throw new Error(
              "skill file paths must be relative, without traversal",
            );
          this.assets.set(`${directory}/${path}`, content);
        }
        skill.source = `file:${directory}`;
      }
  }
  private skillFiles(
    skill: any,
    inline: Record<string, string>,
  ): Map<string, Uint8Array> {
    if (skill.source == null)
      return new Map(
        Object.entries(inline).map(([p, t]) => [p, Buffer.from(t)]),
      );
    const uri = new URL(skill.source);
    if (uri.protocol !== "file:" || !["", "localhost"].includes(uri.hostname))
      throw new Error(`skill source must be a local file URI: ${skill.source}`);
    const root = realpathSync(resolve(decodeURIComponent(uri.pathname)));
    if (!lstatSync(join(root, "SKILL.md")).isFile())
      throw new Error(`skill source has no SKILL.md: ${skill.source}`);
    const files = new Map<string, Uint8Array>();
    function walk(directory: string, prefix = ""): void {
      for (const name of readdirSync(directory).sort()) {
        const path = join(directory, name),
          relative = prefix + name,
          stat = lstatSync(path);
        if (stat.isSymbolicLink())
          throw new Error(`skill capture requires regular files: ${path}`);
        if (stat.isDirectory()) walk(path, `${relative}/`);
        else if (stat.isFile()) files.set(relative, readFileSync(path));
      }
    }
    walk(root);
    return files;
  }
  async error(
    code: ErrorCode,
    message: string,
    options: { subagent?: string | null } = {},
  ): Promise<void> {
    this.check("error", false);
    const now = this.now();
    if (!this.started) {
      this.root.data.steps = [];
      avp(this.root.step(now, "system", message)).error_code = code;
      this.root.stopped("error", now);
      this.ended = true;
      await this.write();
      return;
    }
    avp(this.scope(options.subagent).step(now, "system", message)).error_code =
      code;
  }
  async stop(reason: StopReason, output: JsonValue = null): Promise<void> {
    if (this.ended) return;
    if (!this.started) {
      await this.error("agent_crash", "The run stopped before it started.");
      return;
    }
    const running = [...this.subagents]
      .filter(([, c]) => c.stopReason == null)
      .map(([id]) => id);
    for (const id of [...running].reverse())
      await this.subagentStopped(id, "abandoned");
    for (const [id, call] of this.calls)
      if (!call.returned)
        await this.result(id, UNRETURNED_TEXT, { isError: true });
    if (running.length && reason === "converged") reason = "abandoned";
    this.root.stopped(reason, this.now());
    const last = this.root.data.steps.findLast(
      (s: any) => s.source === "agent",
    )?.message;
    if (
      !(typeof output === "string" && output === last) &&
      (output != null || last != null)
    )
      avp(this.root.data).output = output;
    this.ended = true;
    await this.write();
  }
  image(data: Uint8Array, mediaType: string): Image {
    const extensions: Record<string, string> = {
      "image/png": "png",
      "image/jpeg": "jpg",
      "image/gif": "gif",
      "image/webp": "webp",
    };
    if (!extensions[mediaType])
      throw new Error(`ATIF does not support image media type ${mediaType}`);
    const path = `images/${createHash("sha256").update(data).digest("hex")}.${extensions[mediaType]}`;
    this.assets.set(path, Buffer.from(data));
    return {
      type: "image",
      path,
      media_type: mediaType as Image["media_type"],
    };
  }
  imageBase64(data: string, mediaType: string): Image {
    if (
      !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
        data,
      )
    )
      throw new Error("invalid base64 image");
    return this.image(Buffer.from(data, "base64"), mediaType);
  }
  async step(
    parts: Part[],
    options: {
      usage?: Usage | null;
      modelName?: string | null;
      finishReasons?: string[] | null;
      subagent?: string | null;
    } = {},
  ): Promise<void> {
    this.check("step");
    const doc = this.scope(options.subagent);
    const calls = parts.filter((p): p is Call => p.type === "call");
    const ids = calls.map((c) => c.id);
    const repeated = ids.find(
      (id, i) => this.calls.has(id) || ids.indexOf(id) !== i,
    );
    if (repeated != null)
      throw new RecorderError(`step: tool call ${repeated} was already used`);
    const server = new Set(calls.filter((c) => c.server_side).map((c) => c.id));
    const results = parts.filter(
      (p): p is ServerResult => p.type === "server_result",
    );
    if (results.some((r) => !server.has(r.call_id)))
      throw new RecorderError("step: result for unknown server-side call");
    const [message, metadata] = this.content(
      parts.filter(
        (p): p is Text | Image => p.type === "text" || p.type === "image",
      ),
    );
    const reasoning = parts.filter(
      (p): p is Reasoning => p.type === "reasoning",
    );
    const readable = reasoning.filter((r) => r.text);
    let start = 0;
    const texts: string[] = [],
      reasoningMetadata: any[] = [];
    for (const block of reasoning) {
      const entry: any = {};
      if (block.text) {
        if (readable.length > 1)
          Object.assign(entry, { start, end: start + [...block.text].length });
        start += [...block.text].length + 2;
        texts.push(block.text);
      }
      if (block.signature != null) entry.signature = block.signature;
      if (block.encrypted_content != null)
        entry.encrypted_content = block.encrypted_content;
      reasoningMetadata.push(entry);
    }
    const now = this.now(),
      step = doc.step(now, "agent", message),
      model = doc.data.agent.model_name;
    if (options.modelName != null && options.modelName !== model)
      step.model_name = options.modelName;
    if (texts.length) step.reasoning_content = texts.join("\n\n");
    if (calls.length)
      step.tool_calls = calls.map((c) => ({
        tool_call_id: c.id,
        function_name: c.name,
        arguments: structuredClone(c.arguments),
        ...(c.server_side ? { extra: { avp: { server_side: true } } } : {}),
      }));
    if (results.length)
      step.observation = { results: results.map((r) => this.observation(r)) };
    step.llm_call_count = 1;
    const extra = avp(step);
    extra.duration_ms = ms(doc.last ?? now, now);
    if (options.finishReasons?.length)
      extra.finish_reasons = options.finishReasons;
    if (metadata.length) extra.message_metadata = metadata;
    if (reasoningMetadata.some((e) => Object.keys(e).length))
      extra.reasoning_metadata = reasoningMetadata;
    if (options.usage != null)
      step.metrics = await this.priced(
        metrics(options.usage),
        doc,
        options.modelName ?? model,
      );
    doc.last = now;
    for (const call of calls)
      if (!call.server_side)
        this.calls.set(call.id, {
          document: doc,
          step,
          time: now,
          returned: false,
        });
  }
  private content(parts: (Text | Image)[]): [any, any[]] {
    const metadata: any[] = [];
    for (const [i, part] of parts.entries()) {
      const entry: any = {};
      if (part.type === "text" && part.citations?.length)
        entry.citations = structuredClone(part.citations);
      if (part.type === "text" && part.refusal) entry.refusal = true;
      if (Object.keys(entry).length) metadata.push({ part_index: i, ...entry });
    }
    if (!parts.length) return ["", metadata];
    if (parts.length === 1 && parts[0].type === "text")
      return [parts[0].text, metadata];
    return [
      parts.map((p) => {
        if ("text" in p) return { type: "text", text: p.text };
        if (!this.assets.has(p.path))
          throw new RecorderError(
            `image ${p.path} was not made by this Recorder`,
          );
        return {
          type: "image",
          source: { media_type: p.media_type, path: p.path },
        };
      }),
      metadata,
    ];
  }
  private observation(result: ServerResult): any {
    const [content, metadata] =
      typeof result.content === "string"
        ? [result.content, []]
        : this.content(result.content);
    const data: any = { source_call_id: result.call_id, content };
    if (result.is_error) avp(data).is_error = true;
    if (result.structured_content != null)
      avp(data).structured_content = result.structured_content;
    if (metadata.length) avp(data).content_metadata = metadata;
    return data;
  }
  private async priced(
    metrics: any,
    doc: Document,
    model?: string,
  ): Promise<Metrics> {
    const cached =
      (metrics.cached_tokens ?? 0) +
      (metrics.extra?.avp?.cache_creation_input_tokens ?? 0);
    if (cached > (metrics.prompt_tokens ?? cached))
      throw new RecorderError(
        "step: cached and cache creation tokens exceed prompt_tokens",
      );
    if (metrics.cost_usd != null) {
      avp(metrics).cost_source ??= "reported";
      return metrics;
    }
    if (doc.provider == null || model == null || metrics.prompt_tokens == null)
      return metrics;
    this.prices ??= await loadPrices();
    const cost = computeCost(this.prices, doc.provider, model, metrics);
    if (cost != null) {
      metrics.cost_usd = cost;
      avp(metrics).cost_source = "computed";
    }
    return metrics;
  }
  async result(
    id: string,
    content: string | (Text | Image)[],
    options: { isError?: boolean; structuredContent?: JsonValue } = {},
  ): Promise<void> {
    this.check("result");
    const call = this.calls.get(id);
    if (!call || call.returned)
      throw new RecorderError(
        `result: tool call ${id} is ${call ? "already returned" : "unknown"}`,
      );
    const data = this.observation({
      type: "server_result",
      call_id: id,
      content,
      is_error: options.isError,
      structured_content: options.structuredContent,
    });
    call.returned = true;
    const now = this.now(),
      extra = avp(data);
    extra.finished_at = now.toISOString();
    extra.duration_ms = ms(call.time, now);
    const child = this.subagents.get(id);
    if (child) {
      if (child.stopReason != null)
        extra.is_error = child.stopReason !== "converged";
      data.subagent_trajectory_ref = [
        { trajectory_id: child.data.trajectory_id },
      ];
    }
    (call.step.observation ??= { results: [] }).results.push(data);
    call.document.last = now;
  }
  async subagentStarted(
    id: string,
    name: string,
    prompt: string,
    options: { agent?: Agent } = {},
  ): Promise<void> {
    this.check("subagent_started");
    const call = this.calls.get(id);
    if (!call || call.returned)
      throw new RecorderError(
        `subagent_started: tool call ${id} is unknown or returned`,
      );
    if (this.subagents.has(id))
      throw new RecorderError(`subagent_started: ${id} was already used`);
    const child = this.document(
      `${this.runId}/subagent/${id}`,
      name,
      "unknown",
    );
    let given: any = structuredClone(options.agent ?? {});
    if (!options.agent) {
      const parent = call.document.data.agent;
      if (parent.model_name != null) given.model_name = parent.model_name;
      if (parent.extra?.avp?.model)
        given.extra = {
          avp: { model: structuredClone(parent.extra.avp.model) },
        };
    }
    child.data.agent = { ...given, name, version: "unknown" };
    child.provider = given.extra?.avp?.model?.provider;
    const now = this.now();
    child.last = now;
    avp(child.data).started_at = now.toISOString();
    child.step(now, "user", prompt);
    this.subagents.set(id, child);
    call.document.children.push(child);
    (call.document.data.subagent_trajectories ??= []).push(child.data);
  }
  async subagentStopped(
    id: string,
    reason: StopReason = "converged",
    options: { usage?: Usage | null; modelName?: string | null } = {},
  ): Promise<void> {
    this.check("subagent_stopped");
    const child = this.subagents.get(id);
    if (!child || child.stopReason != null)
      throw new RecorderError(
        `subagent_stopped: subagent ${id} is ${child ? "already stopped" : "unknown"}`,
      );
    for (const [id, grandchild] of this.subagents)
      if (grandchild.stopReason == null && child.children.includes(grandchild))
        await this.subagentStopped(id, "abandoned");
    child.stopped(reason, this.now());
    if (options.usage != null)
      child.reported = totals(
        await this.priced(
          metrics(options.usage),
          child,
          options.modelName ?? child.data.agent.model_name,
        ),
      );
  }
}
