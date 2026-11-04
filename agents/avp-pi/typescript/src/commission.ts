/** Commission values mapped to Pi's native runtime. */
import { createHash } from "node:crypto";
import type {
  Commission,
  EnvSecret,
} from "@agent-voyager-project/sdk/commission";

export const AGENT_NAME = "avp-pi";
export class MissingSecret extends Error {}

export function envSecret(value: EnvSecret): string {
  const found = process.env[value.env];
  if (found === undefined)
    throw new MissingSecret(`the agent's environment has no ${value.env}`);
  return found;
}

export function credential(commission: Commission): string | undefined {
  const value = commission.model.credential;
  return value == null
    ? undefined
    : "proxy" in value
      ? "avp-proxy-stand-in"
      : envSecret(value);
}

export function skillInstructions(commission: Commission): string {
  return (commission.skills ?? [])
    .map(
      (skill) =>
        `## Skill: ${skill.name}\n\n${Object.entries(skill.files)
          .sort(
            ([a], [b]) => Number(b === "SKILL.md") - Number(a === "SKILL.md"),
          )
          .map(([path, text]) => `### ${path}\n\n${text}`)
          .join("\n\n")}`,
    )
    .join("\n\n");
}

export function toolName(
  server: string,
  tool: string,
  taken: Set<string>,
): string {
  const name = `mcp__${server}__${tool}`.replace(/[^A-Za-z0-9_]/g, "_");
  if (name.length <= 64 && !taken.has(name)) return name;
  const digest = createHash("sha256")
    .update(JSON.stringify([server, tool]))
    .digest("hex")
    .slice(0, 14);
  return `${name.slice(0, 49)}_${digest}`;
}
