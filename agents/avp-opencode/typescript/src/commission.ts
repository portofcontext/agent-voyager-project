/** Native configuration built from the SDK run plan. */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve, sep, matchesGlob } from "node:path";
import type {
  Commission,
  EnvSecret,
} from "@agent-voyager-project/sdk/commission";
import type { RunPlan } from "@agent-voyager-project/sdk/utils/run_plan";
import type { PermissionRuleset } from "@opencode-ai/sdk/v2/client";
export const NAME = "avp-opencode";
export const HIDDEN = new Set(["invalid", "websearch"]);
// SDKs compiled into the pinned OpenCode binary; other packages need runtime npm.
export const BUNDLED = new Set([
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
export const BASE = {
  share: "disabled",
  autoupdate: false,
  snapshot: false,
  plugin: [],
  instructions: [],
  lsp: false,
  formatter: false,
  compaction: { auto: false, prune: false },
  permission: { "*": "allow" },
};
export class MissingSecret extends Error {}
export function envSecret(value: EnvSecret, env: NodeJS.ProcessEnv): string {
  const found = env[value.env];
  if (!found)
    throw new MissingSecret(`environment variable ${value.env} is missing`);
  return found;
}
/** Native Permission.disabled filters tool names; resource checks select skills. */
export function permitted(
  rules: PermissionRuleset,
  name: string,
  resource?: string,
): boolean {
  const permission = ["edit", "write", "apply_patch"].includes(name)
    ? "edit"
    : [
          "list_mcp_resources",
          "list_mcp_resource_templates",
          "read_mcp_resource",
        ].includes(name)
      ? "read"
      : name;
  const rule = rules
    .filter(
      (rule) =>
        matchesGlob(permission, rule.permission) &&
        (resource === undefined || matchesGlob(resource, rule.pattern)),
    )
    .at(-1);
  return resource === undefined
    ? !(rule?.pattern === "*" && rule.action === "deny")
    : rule?.action !== "deny";
}
export function configuration(
  c: Commission,
  plan: RunPlan,
  scratch: string,
  env: NodeJS.ProcessEnv,
): Record<string, unknown> {
  const secret = c.model.credential;
  const key =
    secret == null
      ? c.model.provider === "google"
        ? (env.GEMINI_API_KEY ?? env.GOOGLE_API_KEY)
        : undefined
      : "proxy" in secret
        ? secret.proxy
        : envSecret(secret, env);
  const permission = {
    "*": "allow",
    skill: {
      "*": "deny",
      ...Object.fromEntries(
        (plan.started.skills ?? []).map((item) => [item.name, "allow"]),
      ),
    },
  };
  const mcp = Object.fromEntries(
    (c.mcp_servers ?? []).map((server) => [
      server.id,
      server.type === "stdio"
        ? {
            type: "local",
            command: server.command,
            environment: Object.fromEntries(
              Object.entries(server.env ?? {}).map(([name, value]) => [
                name,
                typeof value === "string" ? value : envSecret(value, env),
              ]),
            ),
            enabled: true,
            timeout: 30_000,
          }
        : {
            type: "remote",
            url: server.url,
            headers: Object.fromEntries(
              Object.entries(server.headers ?? {})
                .filter(
                  ([, value]) =>
                    typeof value === "string" || !("proxy" in value),
                )
                .map(([name, value]) => [
                  name,
                  typeof value === "string"
                    ? value
                    : envSecret(value as EnvSecret, env),
                ]),
            ),
            oauth: false,
            enabled: true,
            timeout: 30_000,
          },
    ]),
  );
  const skillsDir = join(scratch, "skills");
  mkdirSync(skillsDir, { recursive: true });
  for (const skill of c.skills ?? [])
    for (const [path, text] of Object.entries(skill.files)) {
      const root = resolve(skillsDir, skill.name),
        target = resolve(root, path);
      if (!target.startsWith(root + sep))
        throw new Error(`skill file escapes its directory: ${path}`);
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, text);
    }
  return {
    ...BASE,
    model: `${c.model.provider}/${c.model.id}`,
    small_model: `${c.model.provider}/${c.model.id}`,
    enabled_providers: [c.model.provider],
    provider: {
      [c.model.provider]: {
        models: { [c.model.id]: {} },
        options: {
          ...(key ? { apiKey: key } : {}),
          ...(c.model.base_url ? { baseURL: c.model.base_url } : {}),
        },
      },
    },
    skills: { paths: [skillsDir] },
    mcp,
    permission,
    agent: {
      build: {
        permission: {
          task: {
            "*": "deny",
            ...Object.fromEntries(
              (plan.started.subagents ?? []).map((item) => [
                item.name,
                "allow",
              ]),
            ),
          },
        },
      },
      title: { disable: true },
      summary: { disable: true },
      compaction: { disable: true },
    },
  };
}
export function toolSwitches(
  off: string[],
  enabled: string[],
): Record<string, boolean> {
  const result = Object.fromEntries(off.map((name) => [name, false]));
  // OpenCode filters exact tool IDs but groups write/apply_patch under the edit
  // permission. Keep that permission when only the edit tool is withheld.
  if (
    off.includes("edit") &&
    enabled.some((name) => ["write", "apply_patch"].includes(name))
  )
    result["edit*"] = true;
  return result;
}
