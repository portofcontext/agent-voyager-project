import { readFileSync } from "node:fs";
import { Ajv2020 } from "ajv/dist/2020.js";
import formats from "ajv-formats";

export const ajv = new Ajv2020({ strict: false, allErrors: true });
formats.default(ajv);
const schema = JSON.parse(
  readFileSync(new URL("./schemas/trajectory.json", import.meta.url), "utf8"),
);
// Python validates AgentName map keys; patternProperties alone leaves unmatched keys open.
const agents = schema.$defs.Commission.properties.agents.anyOf.find(
  (choice: { type?: string }) => choice.type === "object",
);
agents.propertyNames = { pattern: Object.keys(agents.patternProperties)[0] };
ajv.addSchema(schema);

export function eventDefinition(kind: string): string | undefined {
  return Object.hasOwn(schema.discriminator.mapping, kind)
    ? schema.discriminator.mapping[kind].split("/").at(-1)
    : undefined;
}

// Match model_dump(exclude_none=True), preserving nulls inside arbitrary JSON maps.
function clean(value: unknown, node: Record<string, any>): unknown {
  if (node.$ref) return clean(value, schema.$defs[node.$ref.split("/").at(-1)]);
  if (value === null || value === undefined) return value;
  if (node.discriminator && typeof value === "object") {
    const tag = (value as Record<string, unknown>)[
      node.discriminator.propertyName
    ];
    const ref = node.discriminator.mapping[String(tag)];
    if (ref) return clean(value, { $ref: ref });
  }
  if (node.anyOf) {
    const branch = node.anyOf.find((choice: Record<string, any>) => {
      if (choice.$ref)
        return ajv.getSchema(`${schema.$id}${choice.$ref}`)?.(value);
      if (choice.type === "array") return Array.isArray(value);
      if (choice.type === "object")
        return typeof value === "object" && !Array.isArray(value);
      return (
        !choice.type ||
        typeof value === choice.type ||
        (choice.type === "integer" && Number.isInteger(value))
      );
    });
    if (branch) return clean(value, branch);
  }
  if (Array.isArray(value) && node.items)
    return value.map((item) => clean(item, node.items));
  if (
    typeof value === "object" &&
    !Array.isArray(value) &&
    node.type === "object"
  ) {
    return Object.fromEntries(
      Object.entries(value).flatMap(([key, item]) => {
        if (
          node.properties &&
          item == null &&
          !(node.required ?? []).includes(key)
        )
          return [];
        const child =
          node.properties?.[key] ??
          (typeof node.additionalProperties === "object"
            ? node.additionalProperties
            : {});
        return [[key, clean(item, child)]];
      }),
    );
  }
  return value;
}

export function parseDefinition<T>(name: string, value: unknown): T {
  if (name === "ErrorOccurred" || name === "ErrorOccurredEvent") {
    value = structuredClone(value);
    const error =
      name === "ErrorOccurred"
        ? value
        : (value as Record<string, unknown>)?.data;
    if (
      error &&
      typeof error === "object" &&
      "error_code" in error &&
      typeof error.error_code === "string" &&
      !schema.$defs.ErrorOccurred.properties.error_code.enum.includes(
        error.error_code,
      )
    )
      error.error_code = "unknown";
  }
  const validate = ajv.getSchema(`${schema.$id}#/$defs/${name}`);
  if (!validate) throw new Error(`Unknown wire definition ${name}`);
  if (!validate(value)) throw new TypeError(ajv.errorsText(validate.errors));
  return clean(value, schema.$defs[name]) as T;
}
