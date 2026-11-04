/** Commission values mapped to Pi's native runtime. */
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve, sep } from "node:path";
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

/** Materialize the Commission's skill files for Pi's native skill loader. */
export function writeSkills(commission: Commission, root: string): void {
  mkdirSync(root, { recursive: true });
  for (const skill of commission.skills ?? []) {
    const directory = resolve(root, skill.name);
    for (const [path, text] of Object.entries(skill.files)) {
      const target = resolve(directory, path);
      if (!target.startsWith(directory + sep))
        throw new Error(`skill file escapes its directory: ${path}`);
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, text);
    }
  }
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
