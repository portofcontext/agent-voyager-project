import { rm } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { copyData } from "./copy-data.mjs";

const root = new URL("../", import.meta.url);
await rm(new URL("dist/", root), { recursive: true, force: true });
execFileSync(
  process.execPath,
  [
    fileURLToPath(new URL("node_modules/typescript/bin/tsc", root)),
    "-p",
    "tsconfig.json",
  ],
  { cwd: root, stdio: "inherit" },
);
await copyData(root, "dist");
