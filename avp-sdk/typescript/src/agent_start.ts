/** Resolved start configuration, with complete skill contents inline. */
import {
  readFileSync,
  readdirSync,
  lstatSync,
  realpathSync,
  existsSync,
} from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { ajv } from "./validation.js";
import type { AgentStart, Commission } from "./wire.js";
export type { AgentStart, StartedSkill, StartedSubagent } from "./wire.js";
const validate = ajv.compile<AgentStart>(
  JSON.parse(
    readFileSync(
      new URL("./schemas/agent-start.json", import.meta.url),
      "utf8",
    ),
  ),
);
export function parseAgentStart(received: unknown): AgentStart {
  const value =
    typeof received === "string"
      ? JSON.parse(received)
      : structuredClone(received);
  if (!validate(value)) throw new TypeError(ajv.errorsText(validate.errors));
  return value;
}
export function captureStart(
  context: any,
  commission: Commission | undefined,
  runId: string,
): AgentStart {
  const data = structuredClone(context);
  const supplied = new Map(
    (commission?.skills ?? []).map((s) => [s.name, s.files]),
  );
  const connections = new Map(
    (commission?.mcp_servers ?? []).map((s) => [s.id, s]),
  );
  const capture = (items: any[], suppliedSkills = false) => {
    for (const skill of items) {
      if (skill.source) {
        const uri = new URL(skill.source);
        if (
          uri.protocol !== "file:" ||
          !["", "localhost"].includes(uri.hostname)
        )
          throw new TypeError(
            `skill source must be a local file URI: ${skill.source}`,
          );
        const root = realpathSync(
          skill.source.startsWith("file:/")
            ? fileURLToPath(skill.source)
            : resolve(skill.source.slice(5)),
        );
        if (!existsSync(resolve(root, "SKILL.md")))
          throw new Error(`skill source has no SKILL.md: ${skill.source}`);
        const files: Record<string, string | { base64: string }> = {};
        const visit = (directory: string, prefix: string) => {
          for (const name of readdirSync(directory).sort()) {
            const path = resolve(directory, name),
              stat = lstatSync(path);
            if (stat.isSymbolicLink())
              throw new Error(`skill capture requires regular files: ${path}`);
            if (stat.isDirectory()) visit(path, `${prefix}${name}/`);
            else if (stat.isFile()) {
              const bytes = readFileSync(path);
              try {
                files[`${prefix}${name}`] = new TextDecoder("utf-8", {
                  fatal: true,
                  ignoreBOM: true,
                }).decode(bytes);
              } catch {
                files[`${prefix}${name}`] = {
                  base64: bytes.toString("base64"),
                };
              }
            }
          }
        };
        visit(root, "");
        skill.files = files;
      } else if (
        skill.files == null &&
        suppliedSkills &&
        supplied.has(skill.name)
      ) {
        skill.files = structuredClone(supplied.get(skill.name));
      }
    }
  };
  const servers = (items: any[]) =>
    items.map((s) => ({ ...connections.get(s.id), ...s }));
  capture(data.skills ?? [], true);
  if (data.mcp_servers) data.mcp_servers = servers(data.mcp_servers);
  for (const child of data.subagents ?? []) {
    capture(child.skills ?? []);
    if (child.mcp_servers) child.mcp_servers = servers(child.mcp_servers);
  }
  if (commission?.output_schema != null)
    data.output_schema = commission.output_schema;
  return parseAgentStart({ avp_version: "0.1", run_id: runId, ...data });
}
