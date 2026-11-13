/** Run artifact manifests and byte-preserving publication. */
import { createHash, randomUUID } from "node:crypto";
import {
  readFileSync,
  existsSync,
  realpathSync,
  mkdirSync,
  writeFileSync,
  renameSync,
  unlinkSync,
} from "node:fs";
import { resolve, dirname, relative, isAbsolute, basename } from "node:path";
import { ajv } from "./validation.js";
import type { ArtifactManifest } from "./wire.js";
export type { ArtifactManifest, Artifact } from "./wire.js";
export type Role = "input" | "output";
export interface ArtifactFile {
  content: Uint8Array;
  role: Role;
}
const schema = JSON.parse(
  readFileSync(new URL("./schemas/artifacts.json", import.meta.url), "utf8"),
);
const validate = ajv.compile<ArtifactManifest>(schema);
export function digest(content: Uint8Array): string {
  return createHash("sha256").update(content).digest("hex");
}
export function parseArtifacts(value: unknown): ArtifactManifest {
  const manifest =
    typeof value === "string" ? JSON.parse(value) : structuredClone(value);
  if (!validate(manifest)) throw new TypeError(ajv.errorsText(validate.errors));
  if (
    new Set(manifest.artifacts.map((a: any) => a.path)).size !==
    manifest.artifacts.length
  )
    throw new TypeError("artifact paths must be unique");
  return manifest as ArtifactManifest;
}
export function artifactPath(directory: string, name: string): string {
  parseArtifacts({
    avp_version: "0.1",
    run_id: "",
    artifacts: [{ path: name, role: "input", sha256: "0".repeat(64) }],
  });
  const root = resolve(directory),
    target = resolve(root, name);
  function resolved(path: string): string {
    if (existsSync(path)) return realpathSync(path);
    const parent = dirname(path);
    return parent === path ? path : resolve(resolved(parent), basename(path));
  }
  const child = relative(resolved(root), resolved(target));
  if (isAbsolute(child) || child === ".." || child.startsWith("../"))
    throw new TypeError("artifact path escapes the run directory");
  return target;
}
export function atomicWrite(path: string, content: Uint8Array): void {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = resolve(dirname(path), `.${randomUUID()}.tmp`);
  writeFileSync(temporary, content, { flag: "wx" });
  try {
    renameSync(temporary, path);
  } finally {
    if (existsSync(temporary)) unlinkSync(temporary);
  }
}
export function writeArtifacts(
  directory: string,
  runId: string,
  files: Map<string, ArtifactFile>,
): void {
  const manifest = parseArtifacts({
    avp_version: "0.1",
    run_id: runId,
    artifacts: [...files]
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([path, file]) => ({
        path,
        role: file.role,
        sha256: digest(file.content),
      })),
  });
  const manifestPath = resolve(directory, "artifacts.json");
  if (existsSync(manifestPath)) {
    const previous = parseArtifacts(readFileSync(manifestPath, "utf8"));
    if (previous.run_id !== runId)
      throw new TypeError("artifact manifest belongs to a different run");
    const current = new Map(
      manifest.artifacts.map((entry) => [entry.path, entry]),
    );
    if (
      previous.artifacts.some((entry) => {
        const next = current.get(entry.path);
        return (
          !next || next.sha256 !== entry.sha256 || next.role !== entry.role
        );
      })
    )
      throw new TypeError(
        "published artifacts are immutable; use a new path for different content",
      );
  }
  for (const entry of manifest.artifacts) {
    if (entry.path === "artifacts.json")
      throw new TypeError("artifacts.json is reserved for the manifest");
    const path = artifactPath(directory, entry.path),
      bytes = files.get(entry.path)!.content;
    if (existsSync(path)) {
      if (!readFileSync(path).equals(Buffer.from(bytes)))
        throw new Error(
          `artifact already exists with different content: ${entry.path}`,
        );
    } else atomicWrite(path, bytes);
  }
  atomicWrite(
    resolve(directory, "artifacts.json"),
    Buffer.from(`${JSON.stringify(manifest, null, 2)}\n`),
  );
}
export function readArtifacts(
  directory: string,
  runId?: string,
): ArtifactManifest {
  const manifest = parseArtifacts(
    readFileSync(resolve(directory, "artifacts.json"), "utf8"),
  );
  if (runId !== undefined && manifest.run_id !== runId)
    throw new TypeError("artifact manifest belongs to a different run");
  for (const entry of manifest.artifacts) {
    if (
      digest(readFileSync(artifactPath(directory, entry.path))) !== entry.sha256
    )
      throw new Error(`artifact hash mismatch: ${entry.path}`);
  }
  return manifest;
}
