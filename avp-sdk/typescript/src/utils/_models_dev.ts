import { readFileSync } from "node:fs";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, dirname, join } from "node:path";

export const API = "https://models.dev/api.json";

export interface Snapshot {
  readonly source: string;
  readonly fetched: string;
}

export function bundled<T>(name: string, parse: (value: unknown) => T): T {
  return parse(
    JSON.parse(
      readFileSync(new URL(`./data/${name}`, import.meta.url), "utf8"),
    ),
  );
}

export function cachePath(name: string): string {
  return join(
    process.env.XDG_CACHE_HOME || join(homedir(), ".cache"),
    "avp",
    name,
  );
}

export async function fetchCatalog(
  catalog?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  if (catalog && Object.keys(catalog).length > 0) return catalog;
  const response = await fetch(API, {
    headers: { "User-Agent": "avp-typescript-sdk" },
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok)
    throw new Error(`models.dev: ${response.status} ${response.statusText}`);
  return (await response.json()) as Record<string, unknown>;
}

export async function save(snapshot: Snapshot, path: string): Promise<string> {
  await mkdir(dirname(path), { recursive: true });
  const partial = join(dirname(path), `.${basename(path)}.partial`);
  await writeFile(partial, `${JSON.stringify(snapshot, undefined, 1)}\n`);
  await rename(partial, path);
  return path;
}

export async function load<S extends Snapshot>(
  path: string | undefined,
  options: {
    defaultPath: string;
    maxAgeMs?: number;
    parse: (value: unknown) => S;
    bundled: () => S;
    fetch: () => Promise<S>;
  },
): Promise<S> {
  const file = path ?? options.defaultPath;
  let snapshot: S | undefined;
  try {
    snapshot = options.parse(JSON.parse(await readFile(file, "utf8")));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  if (path === undefined) {
    const shipped = options.bundled();
    if (!snapshot || Date.parse(shipped.fetched) > Date.parse(snapshot.fetched))
      snapshot = shipped;
  }
  if (
    options.maxAgeMs !== undefined &&
    (!snapshot || Date.now() - Date.parse(snapshot.fetched) > options.maxAgeMs)
  ) {
    snapshot = await options.fetch();
    await save(snapshot, file);
  }
  if (!snapshot)
    throw Object.assign(new Error(`No snapshot at ${file}`), {
      code: "ENOENT",
    });
  return snapshot;
}
