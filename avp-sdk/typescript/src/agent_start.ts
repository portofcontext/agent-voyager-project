/** Resolved start configuration, with references to saved skill directories. */
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
const schema = JSON.parse(
  readFileSync(new URL("./schemas/agent-start.json", import.meta.url), "utf8"),
);
const validate = ajv.compile<AgentStart>(schema);
const validatePath = ajv.compile<string>(
  schema.$defs.StartedSkill.properties.path,
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
  assets: Map<string, Uint8Array>,
): AgentStart {
  const data = structuredClone(context);
  const captured = new Map<string, Uint8Array>();
  const supplied = new Map(
    (commission?.skills ?? []).map((s) => [s.name, s.files]),
  );
  const connections = new Map(
    (commission?.mcp_servers ?? []).map((s) => [s.id, s]),
  );
  const capture = (items: any[], prefix: string, suppliedSkills = false) => {
    for (const [index, skill] of items.entries()) {
      const name = skill.name.replace(/[^A-Za-z0-9._-]/gu, "-");
      const directory = `${prefix}/${index}-${name}`;
      let inline = skill.files;
      delete skill.files;
      delete skill.path;
      const files = new Map<string, Uint8Array>();
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
        const visit = (directory: string, prefix: string) => {
          for (const name of readdirSync(directory).sort()) {
            const path = resolve(directory, name),
              stat = lstatSync(path);
            if (stat.isSymbolicLink())
              throw new Error(`skill capture requires regular files: ${path}`);
            if (stat.isDirectory()) visit(path, `${prefix}${name}/`);
            else if (stat.isFile()) {
              files.set(`${prefix}${name}`, readFileSync(path));
            }
          }
        };
        visit(root, "");
      } else {
        if (inline == null && suppliedSkills) inline = supplied.get(skill.name);
        for (const [path, content] of Object.entries(inline ?? {})) {
          if (typeof content !== "string")
            throw new TypeError("inline skill content must be text");
          files.set(path, Buffer.from(content, "utf8"));
        }
      }
      for (const [path, bytes] of files) {
        if (!validatePath(path))
          throw new TypeError(
            "skill file paths must be relative, without traversal",
          );
        captured.set(`${directory}/${path}`, bytes);
      }
      if (files.size) skill.path = directory;
    }
  };
  const servers = (items: any[]) =>
    items.map((s) => ({ ...connections.get(s.id), ...s }));
  capture(data.skills ?? [], "skills", true);
  if (data.mcp_servers) data.mcp_servers = servers(data.mcp_servers);
  for (const [index, child] of (data.subagents ?? []).entries()) {
    capture(child.skills ?? [], `skills/subagent-${index}`);
    if (child.mcp_servers) child.mcp_servers = servers(child.mcp_servers);
  }
  if (commission?.output_schema != null)
    data.output_schema = commission.output_schema;
  const started = parseAgentStart({
    avp_version: "0.1",
    run_id: runId,
    ...data,
  });
  for (const [path, bytes] of captured) assets.set(path, bytes);
  return started;
}
