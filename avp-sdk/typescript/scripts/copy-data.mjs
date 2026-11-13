import { copyFile, mkdir, readdir, rm } from "node:fs/promises";

/** Copy package data through its source links, producing standalone regular files. */
export async function copyData(root, output) {
  const data = new URL("src/utils/data/", root);
  const files = (await readdir(data)).filter((name) => name.endsWith(".json"));
  await rm(new URL(`${output}/utils/data/`, root), {
    recursive: true,
    force: true,
  });
  for (const file of [
    ...files.map((name) => `utils/data/${name}`),
    "schemas/trajectory.json",
    "schemas/artifacts.json",
    "schemas/reports.json",
  ]) {
    const target = new URL(`${output}/${file}`, root);
    await mkdir(new URL(".", target), { recursive: true });
    await copyFile(new URL(`src/${file}`, root), target);
  }
}
