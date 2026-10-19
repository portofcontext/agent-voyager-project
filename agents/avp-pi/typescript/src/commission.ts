/**
 * Commission -> Pi configuration.
 *
 * - `model` `<origin>/<id>` resolves in Pi's model catalog as provider
 *   `<origin>`, model `<id>`; an unknown model is `unsupported_model`.
 *   `provider.base_url` redirects that model's endpoint; otherwise a
 *   launcher's `<ORIGIN>_HOST` replaces the endpoint's root and keeps its API
 *   path. A `provider.id` other than the origin is `unsupported_provider`.
 *   Credentials come from Pi's usual sources (the provider's environment
 *   variable, or `auth.json` in Pi's agent directory).
 * - `system_prompt` is appended to Pi's own system prompt, which carries its
 *   tool and skill guidance.
 * - `prompt` is the run's single user message.
 * - Inline `skills` are written to a scratch directory and loaded as Pi
 *   skills; Pi lists them in its system prompt and the model reads them on
 *   demand. Pi's own skill discovery is off.
 * - Inline `mcp_servers` connect through Pi's MCP extension with `direct`
 *   exposure, so their tools (`mcp__<server>__<tool>`) are declared to the
 *   model. Connection values pass through literally; Pi's `${VAR}` and
 *   `!command` expansion does not apply to them.
 * - `enabled_builtin_tools` under `avp-pi` selects among Pi's default tools.
 *   Pi ships no subagents, skills, or MCP servers, so those lists must be
 *   empty.
 * - `output_schema` is ignored: Pi has no structured final output.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

import { preflight, type Commission, type commission as wire } from "@avp/types";
import type { ErrorCode } from "@avp/types/trajectory";

export const AGENT_NAME = "avp-pi";

/** Pi's default tool set, which the descriptor declares. */
export const DEFAULT_TOOLS = ["read", "bash", "edit", "write"] as const;

export type McpEntry = wire.McpServerStdio | wire.McpServerHttp;

export interface RunPlan {
  origin: string;
  modelId: string;
  baseUrl: string | undefined;
  prompt: string;
  appendSystemPrompt: string[];
  /** Pi `tools` allowlist: the enabled built-ins plus every Commission MCP tool. */
  tools: string[];
  mcpServers: McpEntry[];
}

export function fromCommission(commission: Commission): RunPlan {
  const [origin, modelId] = splitModel(commission.model);
  const builtins = commission.enabled_builtin_tools?.[AGENT_NAME] ?? [...DEFAULT_TOOLS];
  return {
    origin,
    modelId,
    baseUrl: commission.provider?.base_url ?? undefined,
    prompt: commission.prompt ?? "",
    appendSystemPrompt: commission.system_prompt ? [commission.system_prompt] : [],
    tools: [...builtins, "mcp__*"],
    mcpServers: (commission.mcp_servers ?? []) as McpEntry[],
  };
}

/**
 * `catalogUrl` moved under the launcher's `<ORIGIN>_HOST`, which stands in for
 * the provider's root: `OPENAI_HOST=http://broker/llm/openai` turns
 * `https://api.openai.com/v1` into `http://broker/llm/openai/v1`.
 */
export function launcherBaseUrl(
  origin: string,
  catalogUrl: string,
  env: NodeJS.ProcessEnv = process.env,
): string | undefined {
  const host = env[`${origin.toUpperCase().replace(/-/g, "_")}_HOST`];
  if (!host) return undefined;
  return host.replace(/\/+$/, "") + new URL(catalogUrl).pathname.replace(/\/+$/, "");
}

export function splitModel(model: string): [string, string] {
  const slash = model.indexOf("/");
  return slash < 0 ? ["", model] : [model.slice(0, slash), model.slice(slash + 1)];
}

/**
 * The spec's pre-turn Commission checks, then the refusals specific to this
 * harness: a provider route it cannot take. Model lookup happens in `run`,
 * against Pi's catalog.
 */
export function failFast(commission: Commission, agentVersion: string): [ErrorCode, string] | undefined {
  const failure = preflight(commission, AGENT_NAME, agentVersion, {
    tools: DEFAULT_TOOLS,
    subagents: [],
    skills: [],
    mcpServers: [],
  });
  if (failure) return failure;
  const [origin] = splitModel(commission.model);
  const provider = commission.provider;
  if (provider && provider.id !== origin) {
    return ["unsupported_provider", `cannot serve ${origin} models via ${JSON.stringify(provider.id)}`];
  }
  return undefined;
}

/** Write each inline skill's files under `root/<id>/`, returning `root`. */
export function writeSkills(skills: readonly wire.Skill[], root: string): string {
  for (const skill of skills) {
    for (const [path, text] of Object.entries(skill.files)) {
      const target = join(root, skill.id, path);
      if (!target.startsWith(join(root, skill.id))) {
        throw new Error(`skill ${skill.id}: file path ${JSON.stringify(path)} escapes the skill`);
      }
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, text);
    }
  }
  return root;
}

/** Pi's registered name for an MCP tool (`mcp__<server>__<tool>`). */
export function mcpToolName(server: string, tool: string): string {
  const clean = (s: string) => s.replace(/[^A-Za-z0-9_]/g, "_");
  return `mcp__${clean(server)}__${clean(tool)}`;
}
