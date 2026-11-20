import { execFileSync } from "node:child_process";
import { readdir, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { copyData } from "./copy-data.mjs";

const root = new URL("../", import.meta.url);
await rm(new URL("dist-test/", root), { recursive: true, force: true });
execFileSync(
  process.execPath,
  [
    fileURLToPath(new URL("node_modules/typescript/bin/tsc", root)),
    "-p",
    "tsconfig.test.json",
  ],
  { cwd: root, stdio: "inherit" },
);
await copyData(root, "dist-test/src");
const tests = (await readdir(new URL("dist-test/tests/", root))).filter(
  (name) => name.endsWith(".test.js"),
);
execFileSync(
  process.execPath,
  ["--test", ...tests.map((file) => `dist-test/tests/${file}`)],
  { cwd: root, stdio: "inherit" },
);
