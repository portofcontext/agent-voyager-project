/**
 * Commission -> Gemini CLI configuration.
 *
 * - `model` must be a `google/<id>` slug; `<id>` is the Gemini model Gemini
 *   CLI requests. Another origin is `unsupported_model`. Gemini CLI reaches
 *   Google through the Gemini API with `GEMINI_API_KEY`; a `provider.id`
 *   other than `google` is `unsupported_provider`, and `provider.base_url`
 *   overrides the endpoint.
 * - `system_prompt` becomes the user-level `GEMINI.md` in the run's private
 *   Gemini CLI home, which Gemini CLI places in its system instruction after
 *   its own prompt.
 * - `prompt` is the run's single user message.
 * - Inline `skills` are written to a scratch directory and registered as
 *   Gemini CLI skills next to its built-in ones; the model loads them with
 *   `activate_skill`.
 * - Inline `mcp_servers` connect through Gemini CLI's own MCP client, so their
 *   tools are `mcp_<server>_<tool>`. Connection values pass through literally.
 * - `enabled_builtin_tools`, `enabled_builtin_skills`, and
 *   `enabled_builtin_subagents` under `avp-gemini-cli` select among Gemini
 *   CLI's defaults. It ships no MCP servers, so that list must be empty.
 * - `output_schema` is ignored: Gemini CLI has no structured final output.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve, sep } from "node:path";

import { preflight, type Commission, type commission as wire } from "@avp/types";
import type { ErrorCode } from "@avp/types/trajectory";

export const AGENT_NAME = "avp-gemini-cli";

/** The model origin Gemini CLI serves. */
export const ORIGIN = "google";

/**
 * Gemini CLI's default headless tool set, in its registry order, which the
 * descriptor declares. `ask_user` is left out, as Gemini CLI's own headless
 * mode leaves it out.
 */
export const DEFAULT_TOOLS = [
  "update_topic",
  "list_directory",
  "read_file",
  "grep_search",
  "glob",
  "replace",
  "write_file",
  "web_fetch",
  "run_shell_command",
  "list_background_processes",
  "read_background_output",
  "google_web_search",
  "write_todos",
  "enter_plan_mode",
  "invoke_agent",
  "activate_skill",
] as const;

/** The subagents Gemini CLI ships, dispatched through `invoke_agent`. */
export const DEFAULT_SUBAGENTS = ["codebase_investigator", "cli_help", "generalist"] as const;

/** The skills Gemini CLI ships. */
export const DEFAULT_SKILLS = ["skill-creator", "antigravity-support"] as const;

/** The tool that dispatches a subagent; its calls open subagent frames. */
export const SUBAGENT_TOOL = "invoke_agent";

/** The tool that loads a skill; it stays while any skill is enabled. */
export const SKILL_TOOL = "activate_skill";

export type McpEntry = wire.McpServerStdio | wire.McpServerHttp;

export interface RunPlan {
  modelId: string;
  baseUrl: string | undefined;
  prompt: string;
  systemPrompt: string | undefined;
  /** Built-in tools to drop from Gemini CLI's registry. */
  excludeTools: string[];
  /** Built-in subagents and skills to keep. */
  subagents: string[];
  skills: string[];
  mcpServers: McpEntry[];
}

export function fromCommission(commission: Commission): RunPlan {
  const [, modelId] = splitModel(commission.model);
  const pick = (map: Record<string, string[]> | null | undefined, all: readonly string[]) =>
    map?.[AGENT_NAME] ?? [...all];
  const tools = new Set(pick(commission.enabled_builtin_tools, DEFAULT_TOOLS));
  return {
    modelId,
    baseUrl: commission.provider?.base_url ?? undefined,
    prompt: commission.prompt ?? "",
    systemPrompt: commission.system_prompt ?? undefined,
    excludeTools: DEFAULT_TOOLS.filter((t) => !tools.has(t)),
    subagents: pick(commission.enabled_builtin_subagents, DEFAULT_SUBAGENTS),
    skills: pick(commission.enabled_builtin_skills, DEFAULT_SKILLS),
    mcpServers: (commission.mcp_servers ?? []) as McpEntry[],
  };
}

export function splitModel(model: string): [string, string] {
  const slash = model.indexOf("/");
  return slash < 0 ? ["", model] : [model.slice(0, slash), model.slice(slash + 1)];
}

/**
 * The spec's pre-turn Commission checks, then the refusals specific to this
 * harness: a model origin or provider route it cannot take.
 */
export function failFast(commission: Commission, agentVersion: string): [ErrorCode, string] | undefined {
  const failure = preflight(commission, AGENT_NAME, agentVersion, {
    tools: DEFAULT_TOOLS,
    subagents: DEFAULT_SUBAGENTS,
    skills: DEFAULT_SKILLS,
    mcpServers: [],
  });
  if (failure) return failure;
  const [origin, modelId] = splitModel(commission.model);
  if (origin !== ORIGIN || !modelId) {
    return ["unsupported_model", `Gemini CLI serves ${ORIGIN}/<model> slugs, not ${JSON.stringify(commission.model)}`];
  }
  const provider = commission.provider;
  if (provider && provider.id !== ORIGIN) {
    return ["unsupported_provider", `cannot serve ${origin} models via ${JSON.stringify(provider.id)}`];
  }
  return undefined;
}

/** Write each inline skill's files under `root/<id>/`, returning `root`. */
export function writeSkills(skills: readonly wire.Skill[], root: string): string {
  mkdirSync(root, { recursive: true });
  for (const skill of skills) {
    const base = resolve(root, skill.id);
    for (const [path, text] of Object.entries(skill.files)) {
      const target = resolve(base, path);
      if (!target.startsWith(base + sep)) {
        throw new Error(`skill ${skill.id}: file path ${JSON.stringify(path)} escapes the skill`);
      }
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, text);
    }
  }
  return root;
}

/** The user-level `GEMINI.md` under a Gemini CLI home, written when there is a system prompt. */
export function writeSystemPrompt(home: string, systemPrompt: string | undefined): void {
  if (!systemPrompt) return;
  const dir = join(home, ".gemini");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "GEMINI.md"), systemPrompt);
}
