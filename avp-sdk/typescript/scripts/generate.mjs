import { readFile, writeFile } from "node:fs/promises";
import { compile } from "json-schema-to-typescript";
import { format } from "prettier";

const root = new URL("../../../", import.meta.url);
const schema = JSON.parse(
  await readFile(new URL("spec/v0.1/trajectory.schema.json", root), "utf8"),
);
const reports = JSON.parse(
  await readFile(
    new URL("../src/schemas/reports.json", import.meta.url),
    "utf8",
  ),
);
const trajectory = structuredClone(schema);
const trajectoryRoot = trajectory.$ref
  ? {}
  : {
      Trajectory: Object.fromEntries(
        Object.entries(trajectory).filter(
          ([k]) => !["$defs", "$id", "$schema"].includes(k),
        ),
      ),
    };
schema.$defs = {
  ...reports.$defs,
  Reports: Object.fromEntries(
    Object.entries(reports).filter(
      ([k]) => !["$defs", "$id", "$schema"].includes(k),
    ),
  ),
  ...schema.$defs,
  ...trajectoryRoot,
};
function prepare(node) {
  if (!node || typeof node !== "object") return;
  delete node.title;
  if (node.default === null) delete node.default;
  if (node.$ref === "#/$defs/JsonValue") {
    for (const key of Object.keys(node)) delete node[key];
    return;
  }
  if (node.$ref) delete node.description;
  for (const field of ["$defs", "properties", "patternProperties"]) {
    for (const child of Object.values(node[field] ?? {})) prepare(child);
  }
  for (const field of ["items", "additionalProperties"]) prepare(node[field]);
  for (const field of ["anyOf", "oneOf", "allOf"])
    for (const child of node[field] ?? []) prepare(child);
}
prepare(schema);
schema.title = "Trajectory";
schema.$defs.avp__commission__Skill.title = "CommissionSkill";
schema.$defs.avp__descriptor__Skill.title = "DescriptorSkill";
const { $defs } = schema;
// The object wrapper makes the generator emit definitions unused by the Event union.
const generated = await compile(
  {
    $defs,
    title: "WireTypes",
    type: "object",
    properties: {},
    additionalProperties: false,
  },
  "WireTypes",
  {
    bannerComment:
      "// Generated from Python SDK reports and upstream ATIF schemas. Do not edit.",
    unreachableDefinitions: true,
    unknownAny: true,
    style: { printWidth: 80, bracketSpacing: true, trailingComma: "all" },
  },
);
const output = await format(
  generated
    .replace(/export interface WireTypes \{\s*\}\n/, "")
    .replace(
      /\n \* This interface was referenced by[^\n]*\n \* via the[^\n]*/g,
      "",
    )
    .replace(/\n \*\n \*\//g, "\n */")
    .replace(/\/\*\*\n \*\/\n/g, ""),
  { parser: "typescript" },
);
const target = new URL("../src/wire.ts", import.meta.url);
if (process.argv.includes("--check")) {
  if ((await readFile(target, "utf8")) !== output)
    throw new Error("Wire types are stale; run npm run generate");
} else {
  await writeFile(target, output);
}
