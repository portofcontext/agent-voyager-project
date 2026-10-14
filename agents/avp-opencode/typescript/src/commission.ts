/**
 * Commission -> OpenCode configuration.
 *
 * - `model` `<origin>/<id>` is OpenCode provider `<origin>`, model `<id>`, from
 *   the model catalog the pinned binary bundles. An origin OpenCode doesn't
 *   know, or whose SDK it doesn't bundle (it would install one from npm), is
 *   `unsupported_provider`; a model missing from that provider is
 *   `unsupported_model`. Credentials come from the provider's environment
 *   variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...).
 * - `provider.base_url` is the provider's `baseURL`. A `provider.id` other
 *   than the origin routes through that OpenCode provider when its catalog
 *   lists the model as `<origin>/<id>` (OpenRouter, say); pricing stays keyed
 *   by the origin.
 * - `system_prompt` rides on the prompt's `system`, appended after
 *   OpenCode's own system prompt.
 * - `prompt` is the session's single user message.
 * - `output_schema` is OpenCode's `json_schema` output format; the structured
 *   result is the run's output.
 * - Inline `skills` are written to a scratch directory listed in
 *   `skills.paths`.
 * - Inline `mcp_servers` are OpenCode `local` (stdio) / `remote` (HTTP)
 *   servers. An HTTP server's `auth` SecretRef becomes a bearer header read
 *   from `AVP_VAULT_<HANDLE>` through OpenCode's `{env:...}` substitution.
 * - `enabled_builtin_tools` / `_subagents` / `_skills` under `avp-opencode`
 *   select among the descriptor's built-ins: tools are switched off on the
 *   prompt, subagents and skills by `deny` permission rules.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, sep } from "node:path";

import { preflight, type Commission, type commission as wire } from "@avp/types";
import type { ErrorCode } from "@avp/types/trajectory";

export const AGENT_NAME = "avp-opencode";

/** How long OpenCode waits for an MCP server to connect and list its tools. */
export const MCP_CONNECT_MS = 30_000;

/**
 * The provider SDKs compiled into the OpenCode binary (`BUNDLED_PROVIDERS` in
 * `packages/opencode/src/provider/provider.ts`). A model on any other SDK is
 * installed from npm at run time, which a sandbox can't do.
 */
export const BUNDLED_SDKS = new Set([
  "@ai-sdk/amazon-bedrock",
  "@ai-sdk/amazon-bedrock/mantle",
  "@ai-sdk/anthropic",
  "@ai-sdk/azure",
  "@ai-sdk/google",
  "@ai-sdk/google-vertex",
  "@ai-sdk/google-vertex/anthropic",
  "@ai-sdk/openai",
  "@ai-sdk/openai-compatible",
  "@openrouter/ai-sdk-provider",
  "@ai-sdk/xai",
  "@ai-sdk/mistral",
  "@ai-sdk/groq",
  "@ai-sdk/deepinfra",
  "@ai-sdk/cerebras",
  "@ai-sdk/cohere",
  "@ai-sdk/gateway",
  "@ai-sdk/togetherai",
  "@ai-sdk/perplexity",
  "@ai-sdk/vercel",
  "@ai-sdk/alibaba",
  "gitlab-ai-provider",
  "@ai-sdk/github-copilot",
  "venice-ai-sdk-provider",
]);

/**
 * The subagents and skills this OpenCode version ships. A Commission that
 * withholds one is enforced in the server config, written before the server
 * can be asked; the seam tests check these against the server's own lists.
 */
export const BUILTIN_SUBAGENTS = ["general", "explore"] as const;
export const BUILTIN_SKILLS = ["customize-opencode"] as const;

/** Registry tools the descriptor leaves out: a repair sink the model never sees, and a search tool off by default. */
export const HIDDEN_TOOLS = new Set(["invalid", "websearch"]);

export type McpEntry = wire.McpServerStdio | wire.McpServerHttp;

/** The surfaces the agent ships, by name (the descriptor's). */
export interface Builtins {
  tools: string[];
  subagents: string[];
  skills: string[];
}

export interface RunPlan {
  origin: string;
  modelId: string;
  /** The OpenCode provider that serves the model (the origin unless `provider.id` routes elsewhere). */
  route: string;
  /** The model's id in `route`'s catalog. */
  routeModel: string;
  baseUrl: string | undefined;
  prompt: string;
  system: string | undefined;
  outputSchema: Record<string, unknown> | undefined;
  mcpServers: McpEntry[];
}

export function fromCommission(commission: Commission): RunPlan {
  const [origin, modelId] = splitModel(commission.model);
  const route = commission.provider?.id ?? origin;
  return {
    origin,
    modelId,
    route,
    routeModel: route === origin ? modelId : `${origin}/${modelId}`,
    baseUrl: commission.provider?.base_url ?? undefined,
    prompt: commission.prompt ?? "",
    system: commission.system_prompt ?? undefined,
    outputSchema: commission.output_schema ?? undefined,
    mcpServers: (commission.mcp_servers ?? []) as McpEntry[],
  };
}

export function splitModel(model: string): [string, string] {
  const slash = model.indexOf("/");
  return slash < 0 ? ["", model] : [model.slice(0, slash), model.slice(slash + 1)];
}

/** The spec's pre-turn Commission checks against the descriptor's surfaces. */
export function failFast(
  commission: Commission,
  agentVersion: string,
  builtins: Builtins,
): [ErrorCode, string] | undefined {
  return preflight(commission, AGENT_NAME, agentVersion, {
    tools: builtins.tools,
    subagents: builtins.subagents,
    skills: builtins.skills,
    mcpServers: [],
  });
}

/** The allow-listed subset of `names` (all of them when the Commission sets no list). */
export function allowed(map: Record<string, string[]> | null | undefined, names: readonly string[]): string[] {
  const list = map?.[AGENT_NAME];
  return list ? names.filter((n) => list.includes(n)) : [...names];
}

/**
 * The OpenCode config for a run: hermetic settings, the provider route, the
 * Commission's MCP servers and skills, and permission rules that auto-allow
 * (the run is sandboxed) except where the Commission withholds a built-in.
 */
export function opencodeConfig(
  plan: RunPlan,
  opts: { skillsDir?: string; deniedSubagents?: string[]; deniedSkills?: string[] } = {},
): Record<string, unknown> {
  const model = `${plan.route}/${plan.routeModel}`;
  const permission: Record<string, unknown> = {
    doom_loop: "allow",
    external_directory: "allow",
    read: "allow",
  };
  if (opts.deniedSubagents?.length) {
    permission.task = Object.fromEntries(opts.deniedSubagents.map((n) => [n, "deny"]));
  }
  if (opts.deniedSkills?.length) {
    permission.skill = Object.fromEntries(opts.deniedSkills.map((n) => [n, "deny"]));
  }
  return {
    share: "disabled",
    autoupdate: false,
    snapshot: false,
    model,
    small_model: model,
    enabled_providers: [plan.route],
    ...(plan.baseUrl ? { provider: { [plan.route]: { options: { baseURL: plan.baseUrl } } } } : {}),
    ...(plan.mcpServers.length > 0 ? { mcp: Object.fromEntries(plan.mcpServers.map((e) => [e.id, mcpConfig(e)])) } : {}),
    ...(opts.skillsDir ? { skills: { paths: [opts.skillsDir] } } : {}),
    permission,
  };
}

function mcpConfig(entry: McpEntry): Record<string, unknown> {
  if (entry.type === "stdio") {
    return {
      type: "local",
      command: [...entry.command, ...(entry.args ?? [])],
      ...(entry.env ? { environment: entry.env } : {}),
      timeout: MCP_CONNECT_MS,
    };
  }
  const headers: Record<string, string> = { ...(entry.headers ?? {}) };
  if (entry.auth) headers.Authorization = `Bearer {env:${vaultVar(entry.auth.vault)}}`;
  return { type: "remote", url: entry.url, headers, oauth: false, timeout: MCP_CONNECT_MS };
}

/** The environment variable a supervisor sets for a SecretRef handle. */
export function vaultVar(handle: string): string {
  return `AVP_VAULT_${handle.toUpperCase().replace(/-/g, "_")}`;
}

/** Write each inline skill's files under `root/<id>/`, returning `root`. */
export function writeSkills(skills: readonly wire.Skill[], root: string): string {
  mkdirSync(root, { recursive: true });
  for (const skill of skills) {
    const base = join(root, skill.id);
    for (const [path, text] of Object.entries(skill.files)) {
      const target = join(base, path);
      if (!target.startsWith(base + sep)) {
        throw new Error(`skill ${skill.id}: file path ${JSON.stringify(path)} escapes the skill`);
      }
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, text);
    }
  }
  return root;
}

/** OpenCode's model-facing name for an MCP tool (`<server>_<tool>`, sanitized). */
export function opencodeMcpName(server: string, tool: string): string {
  const clean = (s: string) => s.replace(/[^a-zA-Z0-9_-]/g, "_");
  return `${clean(server)}_${clean(tool)}`;
}

/** The AVP name for an MCP tool, as the other adapters report it (`mcp__<server>__<tool>`). */
export function avpMcpName(server: string, tool: string): string {
  return `mcp__${server}__${tool}`;
}
