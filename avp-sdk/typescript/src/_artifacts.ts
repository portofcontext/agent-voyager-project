/** Explicit run inputs and artifacts; never crawls the workspace. */
import {
  readFileSync,
  readdirSync,
  lstatSync,
  realpathSync,
  existsSync,
} from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  parseArtifacts,
  digest,
  type ArtifactFile,
  type Role,
} from "./artifacts.js";

export class ArtifactCollection {
  files = new Map<string, ArtifactFile>();
  commission: any = {};
  add(path: string, content: Uint8Array, role: Role): void {
    parseArtifacts({
      avp_version: "0.1",
      run_id: "",
      artifacts: [{ path, role, sha256: digest(content) }],
    });
    if (["artifacts.json", "trajectory.json"].includes(path))
      throw new TypeError(`reserved artifact path: ${path}`);
    const old = this.files.get(path);
    if (
      old &&
      (old.role !== role ||
        !Buffer.from(old.content).equals(Buffer.from(content)))
    )
      throw new TypeError(`artifact is immutable; use a new path: ${path}`);
    this.files.set(path, { content: new Uint8Array(content), role });
  }
  json(path: string, data: unknown, role: Role): void {
    this.add(path, Buffer.from(`${JSON.stringify(data, null, 2)}\n`), role);
  }
  begin(commission: any, descriptor: any): void {
    this.commission = commission ?? {};
    if (commission) {
      this.json("inputs/commission.json", commission, "input");
      for (const skill of commission.skills ?? [])
        for (const [path, content] of Object.entries(skill.files))
          this.add(
            `inputs/skills/${encodeURIComponent(skill.name)}/${path}`,
            Buffer.from(content as string),
            "input",
          );
    }
    this.json("inputs/descriptor.json", descriptor, "input");
  }
  effective(context: any): void {
    const data = structuredClone(context);
    const skills = (items: any[], prefix: string) => {
      for (const skill of items) {
        let destination = `${prefix}/${encodeURIComponent(skill.name)}`;
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
          const visit = (directory: string, output: string) => {
            for (const name of readdirSync(directory).sort()) {
              const path = resolve(directory, name),
                stat = lstatSync(path);
              if (stat.isSymbolicLink())
                throw new Error(
                  `skill capture requires regular files: ${path}`,
                );
              if (stat.isDirectory()) visit(path, `${output}/${name}`);
              else if (stat.isFile())
                this.add(`${output}/${name}`, readFileSync(path), "input");
            }
          };
          visit(root, destination);
        } else if (
          this.files.has(
            `inputs/skills/${encodeURIComponent(skill.name)}/SKILL.md`,
          )
        )
          destination = `inputs/skills/${encodeURIComponent(skill.name)}`;
        else continue;
        skill.source = `file:${destination}`;
      }
    };
    skills(data.skills ?? [], "inputs/skills");
    for (const child of data.subagents ?? [])
      skills(
        child.skills ?? [],
        `inputs/subagents/${encodeURIComponent(child.name)}/skills`,
      );
    if (this.commission.output_schema != null)
      data.output_schema = this.commission.output_schema;
    this.json("inputs/effective-agent.json", data, "input");
  }
}
