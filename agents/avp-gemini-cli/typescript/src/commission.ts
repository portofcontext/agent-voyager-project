/** Values passed to Gemini's native configuration, without serializing secrets. */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve, sep } from "node:path";
import type {
  Commission,
  EnvSecret,
} from "@agent-voyager-project/sdk/commission";

export const NAME = "avp-gemini-cli";
export class MissingSecret extends Error {}
export function environment(secret: EnvSecret): string {
  const value = process.env[secret.env];
  if (!value)
    throw new MissingSecret(`environment variable ${secret.env} is missing`);
  return value;
}
export function credential(commission: Commission): string {
  const secret = commission.model.credential;
  if (secret != null)
    return "proxy" in secret ? secret.proxy : environment(secret);
  const key = process.env.GEMINI_API_KEY;
  if (!key)
    throw new MissingSecret(
      "GEMINI_API_KEY is missing and the Commission has no credential",
    );
  return key;
}
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
