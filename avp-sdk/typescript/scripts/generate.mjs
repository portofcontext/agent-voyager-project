import { readFile, writeFile } from "node:fs/promises";
import { isDeepStrictEqual } from "node:util";
import { compile } from "json-schema-to-typescript";
import { format } from "prettier";

const root = new URL("../../../", import.meta.url);
const schema = JSON.parse(
  await readFile(new URL("spec/v0.1/trajectory.schema.json", root), "utf8"),
);
for (const [file, name, skill] of [
  ["commission", "Commission", "avp__commission__Skill"],
  ["agent-descriptor", "AgentDescriptor", "avp__descriptor__Skill"],
]) {
  const standalone = JSON.parse(
    (
      await readFile(new URL(`spec/v0.1/${file}.schema.json`, root), "utf8")
    ).replaceAll("#/$defs/Skill", `#/$defs/${skill}`),
  );
  for (const [key, definition] of Object.entries(standalone.$defs)) {
    if (
      !isDeepStrictEqual(
        definition,
        schema.$defs[key === "Skill" ? skill : key],
      )
    )
      throw new Error(`${file}: ${key} differs between schemas`);
  }
  const embedded = structuredClone(schema.$defs[name]);
  for (const key of ["$schema", "$id", "$defs", "title", "description"]) {
    delete standalone[key];
    delete embedded[key];
  }
  if (!isDeepStrictEqual(standalone, embedded))
    throw new Error(`${name} differs between schemas`);
}
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
schema.title = "Event";
schema.$defs.avp__commission__Skill.title = "CommissionSkill";
schema.$defs.avp__descriptor__Skill.title = "DescriptorSkill";
const { $defs, $id, $schema, ...event } = schema;
// The object wrapper makes the generator emit definitions unused by the Event union.
const generated = await compile(
  {
    $defs,
    title: "WireTypes",
    type: "object",
    properties: { event },
    additionalProperties: false,
  },
  "WireTypes",
  {
    bannerComment:
      "// Generated from spec/v0.1/trajectory.schema.json. Do not edit.",
    unreachableDefinitions: true,
    unknownAny: true,
    style: { printWidth: 80, bracketSpacing: true, trailingComma: "all" },
  },
);
const output = await format(
  generated
    .replace(/export interface WireTypes \{[\s\S]*?\n\}\n/, "")
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
