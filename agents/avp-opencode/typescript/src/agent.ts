/**
 * The adapter: an `opencode serve` session in, Recorder calls out.
 *
 * OpenCode owns the loop. The adapter starts a hermetic server (`server.ts`),
 * reads the built-in surface from it for the descriptor, maps the Commission
 * into the server's config and the prompt request, then follows the server's
 * event stream (`session.ts`) until the session goes idle. OpenCode is a
 * product: the descriptor declares its default tools, subagents, and skills.
 *
 * Inline MCP servers are connected by OpenCode; the adapter reads their status
 * from it and lists each connected server's tools once, for the tool
 * declarations on `agent_started`.
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
  type PriceTable,
  type Sink,
} from "@avp/types";
import type { ErrorCode, McpServerDecl, SkillDecl, SubagentDecl, ToolDecl } from "@avp/types/trajectory";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport, getDefaultEnvironment } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import type { Event, OpencodeClient } from "@opencode-ai/sdk/v2/client";

import {
  AGENT_NAME,
  allowed,
  avpMcpName,
  BUILTIN_SKILLS,
  BUILTIN_SUBAGENTS,
  BUNDLED_SDKS,
  failFast,
  fromCommission,
  HIDDEN_TOOLS,
  MCP_CONNECT_MS,
  opencodeConfig,
  opencodeMcpName,
  splitModel,
  vaultVar,
  writeSkills,
  type Builtins,
  type McpEntry,
  type RunPlan,
} from "./commission.js";
import { OpencodeServer } from "./server.js";
import { EventClock, SessionTranslator } from "./session.js";

export const AGENT_VERSION: string = JSON.parse(
  readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
).version;

/** Where OpenCode lists a skill compiled into the binary. */
const BUILTIN_SKILL_LOCATION = "<built-in>";

/** OpenCode gates these under one `edit` permission: withholding one withholds all. */
const EDIT_TOOLS = ["edit", "write", "apply_patch"];

/** Models whose tool lists together cover every built-in (OpenCode offers GPT models `apply_patch` instead of `edit` / `write`). */
const SURVEY_MODELS = [
  ["anthropic", "claude-sonnet-4-5"],
  ["openai", "gpt-5"],
] as const;

/** How long to wait for the session to settle after an abort. */
const ABORT_SETTLE_MS = 10_000;

/** Seams for tests and embedders; every field is optional. */
export interface RunOptions {
  /** Aborting it stops OpenCode and closes the trajectory as `interrupted`. */
  signal?: AbortSignal;
  /** Extra environment for the OpenCode server (provider credentials, say). */
  env?: Record<string, string | undefined>;
  /** The `opencode` executable; defaults to the pinned platform package's. */
  binary?: string;
}

interface Surface extends Builtins {
  descriptor: AgentDescriptor;
}

/** What the agent ships with, before any Commission. */
export async function describe(options: Pick<RunOptions, "env" | "binary"> = {}): Promise<AgentDescriptor> {
  const scratch = mkdtempSync(join(tmpdir(), "avp-opencode-"));
  const server = await OpencodeServer.start({
    cwd: process.cwd(),
    scratch,
    config: { share: "disabled", autoupdate: false, snapshot: false, enabled_providers: [] },
    env: options.env,
    binary: options.binary,
  });
  try {
    return (await survey(server.client)).descriptor;
  } finally {
    await server.close();
    rmSync(scratch, { recursive: true, force: true });
  }
}

/** The built-in tools, subagents, and skills a server offers. */
async function survey(client: OpencodeClient): Promise<Surface> {
  const ids = await data(client.tool.ids());
  const lists = await Promise.all(
    SURVEY_MODELS.map(([provider, model]) => data(client.tool.list({ provider, model }))),
  );
  const tools: ToolDecl[] = [];
  for (const id of ids) {
    if (HIDDEN_TOOLS.has(id)) continue;
    const tool = lists.flat().find((t) => t.id === id);
    if (tool) tools.push(toolDecl(tool));
  }
  const subagents: SubagentDecl[] = (await data(client.app.agents()))
    .filter((a) => a.native && a.mode === "subagent" && !a.hidden)
    .map((a) => ({ name: a.name, ...(a.description ? { description: a.description } : {}) }));
  const skills: SkillDecl[] = (await data(client.app.skills()))
    .filter((s) => s.location === BUILTIN_SKILL_LOCATION)
    .map((s) => ({ name: s.name, description: s.description, "avp.source": s.location }));
  return {
    descriptor: {
      agent_name: AGENT_NAME,
      agent_version: AGENT_VERSION,
      spec_version: "0.1",
      tools,
      subagents,
      skills,
    },
    tools: tools.map((t) => t.name),
    subagents: subagents.map((s) => s.name),
    skills: skills.map((s) => s.name),
  };
}

export async function run(commission: Commission, sink: Sink, options: RunOptions = {}): Promise<void> {
  const [origin] = splitModel(commission.model);
  const prices = loadDefaultPrices();
  const clock = new EventClock();
  const rec = new Recorder(sink, {
    runId: commission.run_id,
    provider: origin,
    prices,
    clock,
    dispatchTarget: (name) => (name.startsWith("mcp__") ? "mcp_server" : "local"),
  });
  const plan = fromCommission(commission);
  const cwd = process.cwd();
  const scratch = mkdtempSync(join(tmpdir(), "avp-opencode-"));
  const skillsDir = join(scratch, "skills");
  let server: OpencodeServer | undefined;
  try {
    writeSkills(commission.skills ?? [], skillsDir);
    const config = opencodeConfig(plan, {
      skillsDir,
      deniedSubagents: withheld(commission.enabled_builtin_subagents, BUILTIN_SUBAGENTS),
      deniedSkills: withheld(commission.enabled_builtin_skills, BUILTIN_SKILLS),
    });
    server = await OpencodeServer.start({ cwd, scratch, config, env: options.env, binary: options.binary });
    const surface = await survey(server.client);
    rec.prelude(commission, surface.descriptor);
    await session(rec, clock, prices, server, commission, plan, surface, options);
  } catch (err) {
    if (rec.stopped) throw err;
    const message = err instanceof Error ? err.message : String(err);
    if (!(err instanceof RecorderError)) {
      try {
        rec.prelude(commission, { agent_name: AGENT_NAME, agent_version: AGENT_VERSION, spec_version: "0.1" });
      } catch {
        // The prelude was already written.
      }
    }
    rec.error("agent_crash", message);
    rec.stop("error");
    throw err;
  } finally {
    await server?.close();
    rmSync(scratch, { recursive: true, force: true });
  }
}

/** Everything after the prelude: Commission checks, `agent_started`, the session, `agent_stopped`. */
async function session(
  rec: Recorder,
  clock: EventClock,
  prices: PriceTable,
  server: OpencodeServer,
  commission: Commission,
  plan: RunPlan,
  surface: Surface,
  options: RunOptions,
): Promise<void> {
  const client = server.client;
  const refusal = failFast(commission, AGENT_VERSION, surface) ?? (await route(client, plan));
  if (refusal) {
    rec.error(...refusal);
    rec.stop("error");
    return;
  }

  // Tools for this model, after the Commission's allow-lists.
  const offered = (await data(client.tool.list({ provider: plan.route, model: plan.routeModel }))).filter(
    (t) => surface.tools.includes(t.id),
  );
  let enabled = allowed(commission.enabled_builtin_tools, offered.map((t) => t.id));
  const edits = offered.filter((t) => EDIT_TOOLS.includes(t.id)).map((t) => t.id);
  if (edits.some((t) => !enabled.includes(t))) enabled = enabled.filter((t) => !EDIT_TOOLS.includes(t));
  const subagents = surface.descriptor.subagents!.filter((s) =>
    allowed(commission.enabled_builtin_subagents, surface.subagents).includes(s.name),
  );
  if (subagents.length === 0) enabled = enabled.filter((t) => t !== "task");
  const off = (await data(client.tool.ids())).filter((id) => id !== "invalid" && !enabled.includes(id));

  const mcp = await mcpServers(client, plan.mcpServers, rec);
  const withheldSkills = withheld(commission.enabled_builtin_skills, surface.skills);
  const skills = (await data(client.app.skills()))
    .filter((s) => s.location !== BUILTIN_SKILL_LOCATION || !withheldSkills.includes(s.name))
    .map((s): SkillDecl => ({ name: s.name, description: s.description, "avp.source": s.location }));
  rec.start({
    requestModel: commission.model,
    prompt: plan.prompt,
    systemPrompt: plan.system,
    tools: [...offered.filter((t) => enabled.includes(t.id)).map(toolDecl), ...mcp.tools],
    mcpServers: mcp.decls.length > 0 ? mcp.decls : undefined,
    skills: skills.length > 0 ? skills : undefined,
    subagents: subagents.length > 0 ? subagents : undefined,
    threadId: commission.thread_id ?? undefined,
    tags: commission.tags ?? undefined,
  });

  const providers = await data(client.provider.list());
  if (!providers.connected.includes(plan.route)) {
    const env = providers.all.find((p) => p.id === plan.route)?.env ?? [];
    rec.error("auth_error", `no credentials for ${plan.route}${env.length ? ` (set ${env.join(" or ")})` : ""}`);
    rec.stop("error");
    return;
  }
  if (options.signal?.aborted) {
    rec.stop("interrupted");
    return;
  }

  const created = await data(client.session.create({ title: `avp ${commission.run_id}` }));
  const events = new AbortController();
  const subscription = await client.event.subscribe({}, { signal: events.signal });
  const translator = new SessionTranslator(rec, clock, created.id, {
    toolName: mcp.toolName,
    requestModel: plan.modelId,
    provider: plan.origin,
    prices,
    onPermission: (requestID) => void client.permission.reply({ requestID, reply: "once" }).catch(() => {}),
    onHopeless: () => void client.session.abort({ sessionID: created.id }).catch(() => {}),
  });
  let interrupted = false;
  const onAbort = () => {
    interrupted = true;
    void client.session.abort({ sessionID: created.id }).catch(() => {});
    setTimeout(() => events.abort(), ABORT_SETTLE_MS).unref();
  };
  options.signal?.addEventListener("abort", onAbort, { once: true });
  try {
    const stream = subscription.stream[Symbol.asyncIterator]();
    // The first event confirms the subscription, so nothing is missed.
    await stream.next();
    const sent = await client.session.promptAsync({
      sessionID: created.id,
      model: { providerID: plan.route, modelID: plan.routeModel },
      agent: "build",
      parts: [{ type: "text", text: plan.prompt }],
      ...(plan.system ? { system: plan.system } : {}),
      ...(plan.outputSchema ? { format: { type: "json_schema" as const, schema: plan.outputSchema } } : {}),
      ...(off.length > 0 ? { tools: Object.fromEntries(off.map((id) => [id, false])) } : {}),
    });
    if (sent.error) throw new Error(`opencode rejected the prompt: ${JSON.stringify(sent.error)}`);
    const exited = server.exited.then((why) => {
      throw new Error(`${why}${server.log ? `\n${server.log}` : ""}`);
    });
    while (!translator.idle) {
      const next = await Promise.race([stream.next(), exited]);
      if (next.done) break;
      translator.handle(next.value as Event);
    }
  } finally {
    options.signal?.removeEventListener("abort", onAbort);
    events.abort();
  }

  if (interrupted) {
    translator.flushInterrupted();
    rec.stop("interrupted");
    return;
  }
  const failure = translator.error ?? translator.lastError;
  if (failure) {
    rec.error(...failure);
    rec.stop("error");
    return;
  }
  rec.stop("converged", translator.output);
}

/** Refuse a model OpenCode can't serve from its bundled catalog and SDKs. */
async function route(client: OpencodeClient, plan: RunPlan): Promise<[ErrorCode, string] | undefined> {
  const provider = (await data(client.provider.list())).all.find((p) => p.id === plan.route);
  if (!provider) return ["unsupported_provider", `OpenCode has no provider ${JSON.stringify(plan.route)}`];
  const model = provider.models[plan.routeModel];
  if (!model) return ["unsupported_model", `${plan.route}/${plan.routeModel}: not in OpenCode's model catalog`];
  if (!BUNDLED_SDKS.has(model.api.npm)) {
    return ["unsupported_provider", `${plan.route} needs ${model.api.npm}, which this OpenCode build does not bundle`];
  }
  return undefined;
}

/**
 * MCP status from OpenCode (which dials the Commission's servers), and the
 * tools of each connected server, listed once for the declarations. A server
 * OpenCode couldn't connect is reported and left out.
 */
async function mcpServers(
  client: OpencodeClient,
  entries: readonly McpEntry[],
  rec: Recorder,
): Promise<{ decls: McpServerDecl[]; tools: ToolDecl[]; toolName: (name: string) => string }> {
  const decls: McpServerDecl[] = [];
  const tools: ToolDecl[] = [];
  const names = new Map<string, string>();
  const status = entries.length > 0 ? await data(client.mcp.status()) : {};
  for (const entry of entries) {
    const s = status[entry.id];
    if (s?.status !== "connected") {
      const why = s && "error" in s ? s.error : (s?.status ?? "not connected");
      rec.error("mcp_connect_failed", `${entry.id}: ${why}`);
      decls.push({ id: entry.id, status: "failed" });
      continue;
    }
    decls.push({ id: entry.id, status: "connected" });
    for (const tool of await listTools(entry)) {
      const name = avpMcpName(entry.id, tool.name);
      names.set(opencodeMcpName(entry.id, tool.name), name);
      tools.push({ ...tool, name, "avp.mcp_server_id": entry.id });
    }
  }
  const prefixes = decls
    .filter((d) => d.status === "connected")
    .map((d) => [opencodeMcpName(d.id, ""), d.id] as const);
  const toolName = (name: string) => {
    const known = names.get(name);
    if (known) return known;
    const server = prefixes.find(([prefix]) => name.startsWith(prefix));
    return server ? avpMcpName(server[1], name.slice(server[0].length)) : name;
  };
  return { decls, tools, toolName };
}

/** One server's tools, or none when listing fails (OpenCode's connection is what the run uses). */
async function listTools(entry: McpEntry): Promise<ToolDecl[]> {
  const client = new Client({ name: AGENT_NAME, version: AGENT_VERSION });
  try {
    await client.connect(transport(entry), { timeout: MCP_CONNECT_MS });
    const { tools } = await client.listTools(undefined, { timeout: MCP_CONNECT_MS });
    return tools.map((t) => ({
      name: t.name,
      ...(t.description ? { description: t.description } : {}),
      inputSchema: t.inputSchema,
      ...(t.outputSchema ? { outputSchema: t.outputSchema } : {}),
    }));
  } catch {
    return [];
  } finally {
    await client.close().catch(() => {});
  }
}

function transport(entry: McpEntry): Transport {
  if (entry.type === "stdio") {
    const [command, ...args] = entry.command;
    return new StdioClientTransport({
      command,
      args: [...args, ...(entry.args ?? [])],
      env: { ...getDefaultEnvironment(), ...stringEnv(process.env), ...(entry.env ?? {}) },
      stderr: "ignore",
    });
  }
  const headers: Record<string, string> = { ...(entry.headers ?? {}) };
  const secret = entry.auth ? process.env[vaultVar(entry.auth.vault)] : undefined;
  if (secret) headers.Authorization = `Bearer ${secret}`;
  return new StreamableHTTPClientTransport(new URL(entry.url), { requestInit: { headers } });
}

function toolDecl(tool: { id: string; description: string; parameters: unknown }): ToolDecl {
  return { name: tool.id, description: tool.description, inputSchema: tool.parameters as Record<string, unknown> };
}

/** The built-in names a Commission allow-list leaves out. */
function withheld(map: Record<string, string[]> | null | undefined, names: readonly string[]): string[] {
  const list = map?.[AGENT_NAME];
  return list ? names.filter((n) => !list.includes(n)) : [];
}

function stringEnv(env: NodeJS.ProcessEnv): Record<string, string> {
  return Object.fromEntries(Object.entries(env).filter((e): e is [string, string] => e[1] !== undefined));
}

/** A request's body, or an error carrying the server's reply. */
async function data<T>(request: Promise<{ data?: T; error?: unknown; response?: Response }>): Promise<T> {
  const { data, error, response } = await request;
  if (error === undefined && data !== undefined) return data;
  const status = response ? `${response.status} ${response.url}` : "no response";
  throw new Error(`opencode request failed (${status}): ${JSON.stringify(error)}`);
}
