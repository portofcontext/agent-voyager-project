/**
 * The adapter: Gemini CLI's own headless loop in, Recorder calls out.
 *
 * Gemini CLI owns the loop through `LegacyAgentSession`, the session its
 * headless mode (`gemini -p`) runs on: Gemini client turns, the tool
 * scheduler, MCP, skills, and subagents. The adapter observes three of its
 * hooks without replacing any:
 *
 * - the Gemini client's stream, where each model response ends with one
 *   `Finished` event carrying that response's usage; the thoughts, text, and
 *   tool calls since the previous one are reported as one turn;
 * - the tool scheduler, whose completed calls carry the response parts the
 *   model sees next, reported as tool results (`invoke_agent` calls also open
 *   and close a subagent frame);
 * - the content generator, which attributes subagent model calls (made inside
 *   an `invoke_agent` call) to that call's frame as rolled-up usage.
 *
 * Gemini CLI is a product: the descriptor declares its default headless tools,
 * subagents, and skills, and nothing else. Each run gets a private Gemini CLI
 * home, so no user settings, extensions, policies, skills, OAuth state, or
 * stored keys are read; approval mode is YOLO (runs are sandboxed); telemetry
 * and usage statistics are off. The SDK is imported inside `describe` and
 * `run`, so `ping` stays light.
 */
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  computeCost,
  loadDefaultPrices,
  Recorder,
  RecorderError,
  type AgentDescriptor,
  type Commission,
  type ContentBlock,
  type Sink,
} from "@avp/types";
import type { McpServerDecl, SkillDecl, SubagentDecl, ToolDecl } from "@avp/types/trajectory";
import type {
  CompletedToolCall,
  Config,
  ContentGenerator,
  MCPServerConfig,
  ServerGeminiStreamEvent,
} from "@google/gemini-cli-core";

import {
  AGENT_NAME,
  DEFAULT_SKILLS,
  DEFAULT_SUBAGENTS,
  DEFAULT_TOOLS,
  failFast,
  fromCommission,
  ORIGIN,
  SUBAGENT_TOOL,
  writeSkills,
  writeSystemPrompt,
  type McpEntry,
  type RunPlan,
} from "./commission.js";
import * as translate from "./translate.js";

type Core = typeof import("@google/gemini-cli-core");
type GenerateContentResponse = Awaited<ReturnType<ContentGenerator["generateContent"]>>;

export const AGENT_VERSION: string = JSON.parse(
  readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
).version;

/** The model `describe` configures; the descriptor does not depend on it. */
const DESCRIBE_MODEL = "gemini-2.5-flash";

/** Hooks for tests and embedders; every field is optional. */
export interface RunOptions {
  /**
   * A content generator to call in place of the Gemini API, such as Gemini
   * CLI's own `FakeContentGenerator` (what `gemini --fake-responses` uses).
   */
  contentGenerator?: ContentGenerator;
  /** Aborting it stops Gemini CLI and closes the trajectory as `interrupted`. */
  signal?: AbortSignal;
}

/** What the agent ships with, before any Commission. */
export async function describe(): Promise<AgentDescriptor> {
  const core = await import("@google/gemini-cli-core");
  const scratch = mkdtempSync(join(tmpdir(), "avp-gemini-cli-describe-"));
  const workspace = join(scratch, "workspace");
  mkdirSync(workspace);
  try {
    return await withHome(join(scratch, "home"), async () => {
      const config = await configure(core, { cwd: workspace, sessionId: "describe", modelId: DESCRIBE_MODEL });
      try {
        return {
          agent_name: AGENT_NAME,
          agent_version: AGENT_VERSION,
          spec_version: "0.1",
          tools: tools(core, config, DESCRIBE_MODEL),
          subagents: subagents(config),
          skills: skills(config),
        };
      } finally {
        await config.dispose();
      }
    });
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

export async function run(commission: Commission, sink: Sink, options: RunOptions = {}): Promise<void> {
  const mcpNames = new Set<string>();
  const prices = loadDefaultPrices();
  const rec = new Recorder(sink, {
    runId: commission.run_id,
    provider: ORIGIN,
    prices,
    dispatchTarget: (name) => (mcpNames.has(name) ? "mcp_server" : "local"),
  });
  const descriptor = await describe();
  rec.prelude(commission, descriptor);
  const refusal = failFast(commission, AGENT_VERSION);
  if (refusal) {
    rec.error(...refusal);
    rec.stop("error");
    return;
  }

  const core = await import("@google/gemini-cli-core");
  const { getToolCallContext } = await import("@google/gemini-cli-core/dist/src/utils/toolCallContext.js");
  const plan = fromCommission(commission);
  const scratch = mkdtempSync(join(tmpdir(), "avp-gemini-cli-"));
  const home = join(scratch, "home");
  writeSystemPrompt(home, plan.systemPrompt);
  writeSkills(commission.skills ?? [], join(home, ".gemini", "skills"));

  let config: Config | undefined;
  let session: InstanceType<Core["LegacyAgentSession"]> | undefined;
  const onAbort = () => void session?.abort();
  options.signal?.addEventListener("abort", onAbort, { once: true });
  try {
    await withHome(home, async () => {
      config = await configure(core, {
        cwd: process.cwd(),
        sessionId: commission.run_id,
        modelId: plan.modelId,
        plan,
      });
      await config.refreshAuth(core.AuthType.USE_GEMINI, undefined, plan.baseUrl);
      const cfg = config;
      // Serve the Commission's model as named: Gemini CLI otherwise promotes
      // some Flash and Flash Lite ids to its newest release.
      cfg.hasLatestFlashGAAccess = () => false;
      cfg.hasLatestFlashLiteGAAccess = () => false;
      const generator = options.contentGenerator;
      if (generator) cfg.getContentGenerator = () => generator;

      // MCP servers connected during `initialize`; one that failed is reported
      // and left out (Gemini CLI registers no tools for it).
      const manager = cfg.getMcpClientManager();
      const mcpDecls: McpServerDecl[] = [];
      for (const entry of plan.mcpServers) {
        const client = manager?.getClient(entry.id);
        if (client?.getStatus() === core.MCPServerStatus.CONNECTED) {
          mcpDecls.push({ id: entry.id, status: "connected" });
        } else {
          const reason = manager?.getLastError(entry.id) ?? "could not connect";
          rec.error("mcp_connect_failed", `${entry.id}: ${reason}`);
          mcpDecls.push({ id: entry.id, status: "failed" });
        }
      }
      const declared = tools(core, cfg, plan.modelId);
      for (const t of declared) if (t["avp.mcp_server_id"]) mcpNames.add(t.name);
      const enabledSubagents = subagents(cfg);
      const enabledSkills = skills(cfg);
      rec.start({
        requestModel: commission.model,
        prompt: plan.prompt,
        systemPrompt: core.getCoreSystemPrompt(cfg, cfg.getSystemInstructionMemory()),
        tools: declared,
        mcpServers: mcpDecls.length > 0 ? mcpDecls : undefined,
        subagents: enabledSubagents.length > 0 ? enabledSubagents : undefined,
        skills: enabledSkills.length > 0 ? enabledSkills : undefined,
        sessionId: cfg.getSessionId(),
        threadId: commission.thread_id ?? undefined,
        tags: commission.tags ?? undefined,
      });

      const observer = new Observer(rec, cfg, plan, prices, () => void session?.abort());
      observer.tapContentGenerator(getToolCallContext);
      const client = cfg.getGeminiClient();
      const scheduler = new core.Scheduler({
        context: cfg,
        messageBus: cfg.getMessageBus(),
        getPreferredEditor: () => undefined,
        schedulerId: core.ROOT_SCHEDULER_ID,
      });
      const schedule = scheduler.schedule.bind(scheduler);
      scheduler.schedule = async (requests, signal) => {
        const done = await schedule(requests, signal);
        observer.toolsCompleted(done);
        return done;
      };
      session = new core.LegacyAgentSession({
        config: cfg,
        client: observer.tapClient(client),
        scheduler,
        promptId: cfg.getSessionId(),
      });

      let endReason: string | undefined;
      let fatal: string | undefined;
      if (plan.prompt && !options.signal?.aborted) {
        for await (const event of session.sendStream({ message: { content: [{ type: "text", text: plan.prompt }] } })) {
          if (event.type === "error" && event.fatal) fatal ??= event.message;
          if (event.type === "agent_end") endReason = event.reason;
        }
      }
      if (observer.reportError !== undefined) throw observer.reportError;

      const failure = observer.failure ?? (fatal !== undefined ? classify(fatal) : undefined);
      if (options.signal?.aborted || endReason === "aborted") {
        rec.stop("interrupted");
      } else if (failure) {
        rec.error(failure.code, failure.message);
        rec.stop("error");
      } else if (endReason === "failed" || endReason === "max_turns") {
        rec.error("unknown", `Gemini CLI ended the run: ${endReason}`);
        rec.stop("error");
      } else if (endReason === "refusal") {
        rec.stop("refused", observer.lastText || undefined);
      } else {
        rec.stop("converged", observer.lastText || undefined);
      }
    });
  } catch (err) {
    if (rec.stopped) throw err;
    const message = err instanceof Error ? err.message : String(err);
    const code = err instanceof RecorderError ? "agent_crash" : translate.errorCode(message);
    if (code === "unknown" || code === "agent_crash") {
      rec.error("agent_crash", message);
      rec.stop("error");
      throw err;
    }
    // An expected failure before the first turn (missing credentials, say).
    rec.error(code, message);
    rec.stop("error");
  } finally {
    options.signal?.removeEventListener("abort", onAbort);
    await config?.dispose().catch(() => {});
    rmSync(scratch, { recursive: true, force: true });
  }
}

/** A failure message as an AVP error. */
function classify(message: string, status?: number): { code: ReturnType<typeof translate.errorCode>; message: string } {
  return { code: translate.errorCode(message, status), message };
}

/**
 * Run `fn` with Gemini CLI's home (`GEMINI_CLI_HOME`) at `home`, and its
 * console output kept off stdout as its own CLI does: debug lines dropped,
 * the rest on stderr.
 */
async function withHome<T>(home: string, fn: () => Promise<T>): Promise<T> {
  const previous = process.env.GEMINI_CLI_HOME;
  const saved = { log: console.log, info: console.info, debug: console.debug };
  process.env.GEMINI_CLI_HOME = home;
  console.log = console.info = console.error;
  console.debug = () => {};
  try {
    return await fn();
  } finally {
    Object.assign(console, saved);
    if (previous === undefined) delete process.env.GEMINI_CLI_HOME;
    else process.env.GEMINI_CLI_HOME = previous;
  }
}

/**
 * A Gemini CLI `Config` as its headless mode builds one from empty settings,
 * with the Commission's selections applied, initialized (MCP servers
 * connected, skills and subagents loaded).
 */
async function configure(
  core: Core,
  opts: { cwd: string; sessionId: string; modelId: string; plan?: RunPlan },
): Promise<Config> {
  const { plan } = opts;
  // Gemini CLI's headless mode always drops `ask_user`.
  const excludeTools = ["ask_user", ...(plan?.excludeTools ?? [])];
  const mcpServers = Object.fromEntries((plan?.mcpServers ?? []).map((e) => [e.id, mcpConfig(core, e)]));
  const subagents = new Set(plan?.subagents ?? DEFAULT_SUBAGENTS);
  const skills = new Set(plan?.skills ?? DEFAULT_SKILLS);
  const policyEngineConfig = await core.createPolicyEngineConfig(
    { tools: { exclude: excludeTools }, mcpServers },
    core.ApprovalMode.YOLO,
    undefined,
    false,
  );
  const config = new core.Config({
    sessionId: opts.sessionId,
    targetDir: opts.cwd,
    cwd: opts.cwd,
    debugMode: false,
    model: opts.modelId,
    approvalMode: core.ApprovalMode.YOLO,
    policyEngineConfig,
    interactive: false,
    trustedFolder: true,
    usageStatisticsEnabled: false,
    telemetry: { enabled: false },
    excludeTools,
    mcpServers,
    extensionLoader: new core.SimpleExtensionLoader([]),
    enableHooks: false,
    agents: {
      overrides: Object.fromEntries(
        DEFAULT_SUBAGENTS.filter((name) => !subagents.has(name)).map((name) => [name, { enabled: false }]),
      ),
    },
    disabledSkills: DEFAULT_SKILLS.filter((name) => !skills.has(name)),
  });
  await config.initialize();
  return config;
}

/** A Commission MCP entry as Gemini CLI server config, values passed literally. */
function mcpConfig(core: Core, entry: McpEntry): MCPServerConfig {
  if (entry.type === "stdio") {
    const [command, ...args] = entry.command;
    return new core.MCPServerConfig(command, [...args, ...(entry.args ?? [])], entry.env ?? undefined);
  }
  return new core.MCPServerConfig(
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    entry.url,
    entry.headers ?? undefined,
  );
}

/** The tool declarations the model sees, MCP tools tagged with their server. */
function tools(core: Core, config: Config, modelId: string): ToolDecl[] {
  const registry = config.getToolRegistry();
  const servers = new Map<string, string>();
  for (const tool of registry.getAllTools()) {
    if (tool instanceof core.DiscoveredMCPTool) servers.set(tool.name, tool.serverName);
  }
  return registry.getFunctionDeclarations(modelId).map((d) => ({
    name: d.name ?? "",
    description: d.description,
    inputSchema: plain(d.parametersJsonSchema ?? d.parameters),
    ...(servers.has(d.name ?? "") ? { "avp.mcp_server_id": servers.get(d.name ?? "") } : {}),
  }));
}

function subagents(config: Config): SubagentDecl[] {
  return config
    .getAgentRegistry()
    .getAllDefinitions()
    .map((a) => ({
      name: a.name,
      description: a.description,
      ...(a.kind === "local" ? { inputSchema: plain(a.inputConfig?.inputSchema) } : {}),
    }));
}

function skills(config: Config): SkillDecl[] {
  return config
    .getSkillManager()
    .getSkills()
    .map((s) => ({ name: s.name, description: s.description }));
}

/** A JSON copy of a schema object. */
function plain(schema: unknown): Record<string, unknown> {
  return JSON.parse(JSON.stringify(schema ?? {}));
}

/** Accumulated usage of one subagent frame's model calls. */
interface ChildUsage {
  input: number;
  output: number;
  cost: number;
  turns: number;
}

/**
 * Turns Gemini CLI's native events into Recorder calls. Recorder rejections
 * are adapter bugs: the first one is kept in `reportError`, the session is
 * aborted, and `run` rethrows it.
 */
class Observer {
  /** A provider failure seen on the stream, reported when the run ends. */
  failure: { code: ReturnType<typeof translate.errorCode>; message: string } | undefined;
  reportError: unknown;
  lastText = "";

  private content: ContentBlock[] = [];
  private startedAt = performance.now();
  private mainModel: string | undefined;
  /** Tool calls reported in a turn and not yet resulted. */
  private readonly pending = new Set<string>();
  /** Open subagent frames, by `invoke_agent` call id, in opening order. */
  private readonly frames = new Map<string, ChildUsage>();

  constructor(
    private readonly rec: Recorder,
    private readonly config: Config,
    private readonly plan: RunPlan,
    private readonly prices: ReturnType<typeof loadDefaultPrices>,
    private readonly abort: () => void,
  ) {}

  /** The Gemini client with its message stream observed. */
  tapClient<T extends object>(client: T): T {
    const self = this;
    return new Proxy(client, {
      get(target, prop) {
        const value = Reflect.get(target, prop, target);
        if (prop === "sendMessageStream") {
          return (...args: unknown[]) => self.observe((value as (...a: unknown[]) => AsyncGenerator<ServerGeminiStreamEvent>).apply(target, args));
        }
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
  }

  /**
   * Observe the content generator: the main model's served version, and
   * subagent calls attributed to the `invoke_agent` call they run under.
   */
  tapContentGenerator(callContext: () => { callId: string } | undefined): void {
    const inner = this.config.getContentGenerator();
    const self = this;
    const tapped: ContentGenerator = new Proxy(inner, {
      get(target, prop) {
        const value = Reflect.get(target, prop, target);
        if (prop === "generateContentStream") {
          return async (req: { model: string }, promptId: string, role: string) => {
            const callId = callContext()?.callId;
            const stream: AsyncGenerator<GenerateContentResponse> = await value.call(target, req, promptId, role);
            return (async function* () {
              let last: GenerateContentResponse | undefined;
              try {
                for await (const chunk of stream) {
                  if (role === "main" && chunk.modelVersion) self.mainModel = chunk.modelVersion;
                  if (chunk.usageMetadata) last = chunk;
                  yield chunk;
                }
              } finally {
                if (role === "subagent") self.childCall(callId, last?.modelVersion ?? req.model, last);
              }
            })();
          };
        }
        if (prop === "generateContent") {
          return async (req: { model: string }, promptId: string, role: string) => {
            const callId = callContext()?.callId;
            const response: GenerateContentResponse = await value.call(target, req, promptId, role);
            if (role === "subagent") self.childCall(callId, response.modelVersion ?? req.model, response);
            return response;
          };
        }
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
    this.config.getContentGenerator = () => tapped;
  }

  /** Report the scheduler's completed calls: subagent frames, then results. */
  toolsCompleted(done: readonly CompletedToolCall[]): void {
    this.guard(() => {
      for (const call of done) {
        const id = call.request.callId;
        if (!this.pending.delete(id)) continue;
        const content = translate.toolResultContent(call.response.responseParts ?? []);
        const isError = call.response.error !== undefined || call.status !== "success";
        const child = this.frames.get(id);
        if (child) {
          this.frames.delete(id);
          const text = content.map((b) => (b.type === "text" ? b.text : "")).join("");
          this.rec.subagentResult(id, text, {
            reason: call.status === "cancelled" ? "interrupted" : isError ? "error" : "converged",
            usage: {
              tokens_input: child.input,
              tokens_output: child.output,
              cost_usd: child.cost,
              turns: child.turns,
            },
          });
        }
        this.rec.toolResult(id, content, { isError });
      }
    });
  }

  private async *observe(stream: AsyncGenerator<ServerGeminiStreamEvent>): AsyncGenerator<ServerGeminiStreamEvent> {
    this.startedAt = performance.now();
    for await (const event of stream) {
      this.guard(() => this.onEvent(event));
      yield event;
    }
  }

  private onEvent(event: ServerGeminiStreamEvent): void {
    switch (event.type) {
      case "retry":
        // Gemini CLI retries the request; what streamed so far is discarded.
        this.content = [];
        break;
      case "thought":
        this.append({ type: "thinking", thinking: translate.thoughtText(event.value.subject, event.value.description) });
        break;
      case "content":
        this.append({ type: "text", text: event.value });
        break;
      case "tool_call_request":
        this.content.push({ type: "tool_use", id: event.value.callId, name: event.value.name, input: event.value.args });
        break;
      case "finished":
        this.finish(event.value.reason, event.value.usageMetadata);
        break;
      case "error": {
        const error = event.value.error as { message?: string; status?: number } | undefined;
        this.failure ??= classify(error?.message ?? String(event.value.error), error?.status);
        this.content = [];
        break;
      }
      case "invalid_stream":
        this.failure ??= classify(event.value.message || `invalid stream: ${event.value.type}`);
        this.content = [];
        break;
      case "context_window_will_overflow":
        this.failure ??= {
          code: "context_limit",
          message: `context window will overflow (estimated ${event.value.estimatedRequestTokenCount} tokens, ${event.value.remainingTokenCount} remaining)`,
        };
        break;
      default:
        break;
    }
  }

  /** Append a block, merging a text or thinking chunk into the previous one. */
  private append(block: ContentBlock): void {
    const last = this.content.at(-1);
    if (last?.type === "text" && block.type === "text") last.text += block.text;
    else if (last?.type === "thinking" && block.type === "thinking") last.thinking += `\n${block.thinking}`;
    else this.content.push(block);
  }

  /** One complete model response: report it as a turn. */
  private finish(reason: string | undefined, usage: translate.GeminiUsage | undefined): void {
    const content = this.content;
    this.content = [];
    const model = this.mainModel ?? this.config.getGeminiClient().getCurrentSequenceModel() ?? this.plan.modelId;
    this.rec.assistant(content, translate.usage(usage), {
      model,
      requestModel: this.plan.modelId,
      finishReasons: reason ? [reason] : undefined,
      durationMs: Math.max(0, Math.trunc(performance.now() - this.startedAt)),
    });
    this.startedAt = performance.now();
    const text = content.map((b) => (b.type === "text" ? b.text : "")).join("");
    if (text) this.lastText = text;
    for (const b of content) {
      if (b.type !== "tool_use") continue;
      this.pending.add(b.id);
      if (b.name === SUBAGENT_TOOL) {
        const input = b.input as Record<string, unknown>;
        this.frames.set(b.id, { input: 0, output: 0, cost: 0, turns: 0 });
        this.rec.subagentStart(b.id, String(input["agent_name"] ?? SUBAGENT_TOOL), { input });
      }
    }
  }

  /** Roll a subagent model call up onto its frame (else the latest open one). */
  private childCall(callId: string | undefined, model: string, response: GenerateContentResponse | undefined): void {
    const frame = (callId && this.frames.get(callId)) || [...this.frames.values()].at(-1);
    if (!frame) return;
    const u = translate.usage(response?.usageMetadata);
    const [cost] = computeCost(ORIGIN, model, u.input_tokens, u.output_tokens, u.cache_read_input_tokens ?? 0, 0, this.prices);
    frame.input += u.input_tokens;
    frame.output += u.output_tokens;
    frame.cost += cost;
    frame.turns += 1;
  }

  private guard(fn: () => void): void {
    if (this.reportError !== undefined) return;
    try {
      fn();
    } catch (err) {
      this.reportError = err;
      this.abort();
    }
  }
}
