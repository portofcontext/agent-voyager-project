/** Publish run documents and ATIF-referenced files. */
import {
  readFileSync,
  existsSync,
  realpathSync,
  mkdirSync,
  writeFileSync,
  renameSync,
  unlinkSync,
} from "node:fs";
import { resolve, dirname, basename, relative, isAbsolute } from "node:path";
import { randomUUID } from "node:crypto";
import { isDeepStrictEqual } from "node:util";
export function localPath(directory: string, name: string): string {
  if (
    !name ||
    /[\\:\x00]/.test(name) ||
    name.split("/").some((p) => ["", ".", ".."].includes(p))
  )
    throw new TypeError("file path must be relative to the run directory");
  const root = realpathSync(directory),
    target = resolve(root, name);
  let ancestor = target;
  while (!existsSync(ancestor)) ancestor = dirname(ancestor);
  const rel = relative(root, realpathSync(ancestor));
  if (isAbsolute(rel) || rel === ".." || rel.startsWith("../"))
    throw new TypeError("file path escapes the run directory");
  return target;
}
export function atomicWrite(path: string, content: Uint8Array): void {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = resolve(
    dirname(path),
    `.${basename(path)}.${randomUUID()}.tmp`,
  );
  try {
    writeFileSync(temporary, content, { flag: "wx" });
    renameSync(temporary, path);
  } finally {
    if (existsSync(temporary)) unlinkSync(temporary);
  }
}
export function writeDocument(
  directory: string,
  name: string,
  data: unknown,
  parse: (value: unknown) => unknown,
): void {
  const path = localPath(directory, name);
  if (existsSync(path)) {
    if (!isDeepStrictEqual(parse(JSON.parse(readFileSync(path, "utf8"))), data))
      throw new Error(
        `run document already exists with different content: ${name}`,
      );
  } else atomicWrite(path, Buffer.from(`${JSON.stringify(data, null, 2)}\n`));
}
