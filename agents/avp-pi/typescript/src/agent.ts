/**
 * The adapter: Pi session events in, Recorder calls out.
 *
 * Pi owns the loop (`AgentSession.prompt`). Each assistant `message_end` is one
 * complete inference and is reported as one turn; each `tool_execution_end`
 * is reported as its tool result. Pi is a product: the descriptor declares
 * its default tools and nothing else.
 *
 * Pi runs with in-memory settings and sessions, no discovered extensions,
 * prompt templates, or skills, and install telemetry off. It reads
 * credentials and context files (`AGENTS.md`) as it normally does. The SDK
 * is imported inside `describe` and `run`, so `ping` stays light.
 */
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  loadDefaultPrices,
  Recorder,
  RecorderError,
  type AgentDescriptor,
  type Commission,
  type Sink,
} from "@avp/types";
import type { McpServerDecl, SkillDecl, ToolDecl } from "@avp/types/trajectory";
import type { AssistantMessage } from "@earendil-works/pi-ai";
import type { LoadedMcpConfig, ModelRuntime } from "@earendil-works/pi-coding-agent";
import { McpClient, StdioTransport, StreamableHttpTransport, type McpTransport } from "@earendil-works/pi-mcp";

import {
  AGENT_NAME,
  DEFAULT_TOOLS,
  failFast,
  fromCommission,
  mcpToolName,
  splitModel,
  writeSkills,
  type McpEntry,
} from "./commission.js";
import * as translate from "./translate.js";

export const AGENT_VERSION: string = JSON.parse(
  readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
).version;

/** How long to wait for an MCP server to connect and list its tools. */
const MCP_CONNECT_MS = 30_000;

/** Seams for tests and embedders; every field is optional. */
export interface RunOptions {
  /** Pi's agent directory (credentials, MCP sign-ins). Defaults to Pi's own. */
  agentDir?: string;
  /** A configured model runtime, such as one with a scripted provider. */
  modelRuntime?: ModelRuntime;
  /** Aborting it stops Pi and closes the trajectory as `interrupted`. */
  signal?: AbortSignal;
}

/** What the agent ships with, before any Commission. */
export async function describe(): Promise<AgentDescriptor> {
  const pi = await import("@earendil-works/pi-coding-agent");
  const cwd = process.cwd();
  const factories = {
    read: pi.createReadTool,
    bash: pi.createBashTool,
    edit: pi.createEditTool,
    write: pi.createWriteTool,
  };
  return {
    agent_name: AGENT_NAME,
    agent_version: AGENT_VERSION,
    spec_version: "0.1",
    tools: DEFAULT_TOOLS.map((name) => {
      const tool = factories[name](cwd);
      return {
        name: tool.name,
        description: tool.description,
        inputSchema: plain(tool.parameters),
      };
    }),
  };
}

export async function run(commission: Commission, sink: Sink, options: RunOptions = {}): Promise<void> {
  const [origin] = splitModel(commission.model);
  const rec = new Recorder(sink, {
    runId: commission.run_id,
    provider: origin,
    prices: loadDefaultPrices(),
    dispatchTarget: (name) => (name.startsWith("mcp__") ? "mcp_server" : "local"),
  });
  const descriptor = await describe();
  rec.prelude(commission, descriptor);
  const refusal = failFast(commission, AGENT_VERSION);
  if (refusal) {
    rec.error(...refusal);
    rec.stop("error");
    return;
  }

  process.env.PI_TELEMETRY ??= "0";
  const pi = await import("@earendil-works/pi-coding-agent");
  const plan = fromCommission(commission);
  const cwd = process.cwd();
  const agentDir = options.agentDir ?? pi.getAgentDir();
  const modelRuntime =
    options.modelRuntime ??
    (await pi.ModelRuntime.create({ authPath: join(agentDir, "auth.json"), modelsPath: null }));
  const found = modelRuntime.getModel(plan.origin, plan.modelId);
  if (!found) {
    rec.error("unsupported_model", `${commission.model}: not in Pi's model catalog`);
    rec.stop("error");
    return;
  }
  const model = plan.baseUrl ? { ...found, baseUrl: plan.baseUrl } : found;

  const scratch = mkdtempSync(join(tmpdir(), "avp-pi-"));
  let session: Awaited<ReturnType<typeof pi.createAgentSession>>["session"] | undefined;
  const onAbort = () => void session?.abort();
  options.signal?.addEventListener("abort", onAbort, { once: true });
  try {
    const mcp = await dial(plan.mcpServers, rec);
    const skillsDir = writeSkills(commission.skills ?? [], join(scratch, "skills"));
    const settingsManager = pi.SettingsManager.inMemory({ enableInstallTelemetry: false });
    const byName = new Map(mcp.reachable.map((e) => [e.id, e]));
    const mcpConfig: LoadedMcpConfig = {
      servers: mcp.reachable.map((e) => ({
        name: e.id,
        config: e.type === "stdio" ? { command: e.command[0]!, exposure: "direct" } : { url: e.url, exposure: "direct" },
        source: "avp-commission",
        scope: "extension",
      })),
      errors: [],
      autoEnableCodemode: false,
    };
    const loader = new pi.DefaultResourceLoader({
      cwd,
      agentDir,
      settingsManager,
      noExtensions: true,
      extensionFactories:
        mcp.reachable.length > 0
          ? [
              {
                name: "avp-mcp",
                factory: pi.createMcpExtension({
                  loadConfig: () => mcpConfig,
                  createTransport: (entry) => transport(byName.get(entry.name)!),
                  logPath: join(scratch, "mcp.log"),
                  startupWaitMs: MCP_CONNECT_MS,
                }),
              },
            ]
          : [],
      noPromptTemplates: true,
      noThemes: true,
      skillsOverride: () => pi.loadSkillsFromDir({ dir: skillsDir, source: "avp-commission" }),
      appendSystemPromptOverride: () => plan.appendSystemPrompt,
    });
    await loader.reload();
    ({ session } = await pi.createAgentSession({
      cwd,
      agentDir,
      model,
      modelRuntime,
      resourceLoader: loader,
      tools: plan.tools,
      sessionManager: pi.SessionManager.inMemory(cwd),
      settingsManager,
    }));
    await session.bindExtensions({});

    const enabled = new Set(plan.tools);
    const skills: SkillDecl[] = loader
      .getSkills()
      .skills.map((s) => ({ name: s.name, description: s.description }));
    rec.start({
      requestModel: commission.model,
      prompt: plan.prompt,
      systemPrompt: session.systemPrompt,
      tools: [...(descriptor.tools ?? []).filter((t) => enabled.has(t.name)), ...mcp.tools],
      mcpServers: mcp.decls.length > 0 ? mcp.decls : undefined,
      skills: skills.length > 0 ? skills : undefined,
      threadId: commission.thread_id ?? undefined,
      tags: commission.tags ?? undefined,
    });

    const pending = new Set<string>();
    let startedAt = performance.now();
    let last: AssistantMessage | undefined;
    let reportError: unknown;
    const unsubscribe = session.subscribe((event) => {
      if (reportError !== undefined) return;
      try {
        if (event.type === "message_start" && event.message.role === "assistant") {
          startedAt = performance.now();
        } else if (event.type === "message_end" && event.message.role === "assistant") {
          const m = event.message;
          last = m;
          rec.assistant(translate.content(m.content), translate.usage(m.usage), {
            model: m.responseModel ?? m.model,
            requestModel: m.model,
            finishReasons: translate.finishReasons(m),
            durationMs: Math.max(0, Math.trunc(performance.now() - startedAt)),
          });
          for (const b of m.content) if (b.type === "toolCall") pending.add(b.id);
        } else if (event.type === "tool_execution_end" && pending.delete(event.toolCallId)) {
          rec.toolResult(event.toolCallId, translate.content(event.result?.content ?? []), {
            isError: event.isError,
          });
        }
      } catch (err) {
        // A Recorder rejection is an adapter bug: stop the run and surface it.
        reportError = err;
        void session?.abort();
      }
    });
    try {
      if (plan.prompt && !options.signal?.aborted) await session.prompt(plan.prompt);
    } finally {
      unsubscribe();
    }
    if (reportError !== undefined) throw reportError;

    if (last?.stopReason === "error") {
      const message = last.errorMessage || "provider error";
      rec.error(translate.errorCode(message), message);
      rec.stop("error");
    } else if (last?.stopReason === "aborted" || options.signal?.aborted) {
      rec.stop("interrupted");
    } else {
      rec.stop("converged", session.getLastAssistantText() || undefined);
    }
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
    if (session) {
      // As Pi's own runtime does on quit: `session_shutdown` lets extensions
      // (MCP connections and their server processes) close before dispose.
      if (session.extensionRunner.hasHandlers("session_shutdown")) {
        await session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" }).catch(() => {});
      }
      session.dispose();
    }
    rmSync(scratch, { recursive: true, force: true });
  }
}

/** A transport built from the Commission entry's literal values. */
function transport(entry: McpEntry): McpTransport {
  if (entry.type === "stdio") {
    const [command, ...args] = entry.command;
    return new StdioTransport({
      command: command!,
      args: [...args, ...(entry.args ?? [])],
      env: entry.env ?? undefined,
      inheritEnv: true,
      stderr: "pipe",
    });
  }
  return new StreamableHttpTransport({ url: entry.url, headers: entry.headers ?? undefined });
}

/**
 * Connect to each inline MCP server once to list its tools before the run
 * starts. A server that fails is reported and left out of the run.
 */
async function dial(
  entries: readonly McpEntry[],
  rec: Recorder,
): Promise<{ reachable: McpEntry[]; decls: McpServerDecl[]; tools: ToolDecl[] }> {
  const reachable: McpEntry[] = [];
  const decls: McpServerDecl[] = [];
  const tools: ToolDecl[] = [];
  for (const entry of entries) {
    const client = new McpClient({ name: AGENT_NAME, version: AGENT_VERSION, requestTimeoutMs: MCP_CONNECT_MS });
    try {
      await client.connect(transport(entry));
      for (const t of await client.listTools()) {
        tools.push({
          name: mcpToolName(entry.id, t.name),
          description: t.description,
          inputSchema: t.inputSchema,
          "avp.mcp_server_id": entry.id,
        });
      }
      reachable.push(entry);
      decls.push({ id: entry.id, status: "connected" });
    } catch (err) {
      rec.error("mcp_connect_failed", `${entry.id}: ${err instanceof Error ? err.message : String(err)}`);
      decls.push({ id: entry.id, status: "failed" });
    } finally {
      await client.close().catch(() => {});
    }
  }
  return { reachable, decls, tools };
}

/** A JSON copy of a schema object (drops TypeBox's symbol keys). */
function plain(schema: unknown): Record<string, unknown> {
  return JSON.parse(JSON.stringify(schema ?? {}));
}
