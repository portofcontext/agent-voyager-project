import type { ModelRef } from "../commission.js";
import type { CostSource } from "../trajectory.js";
import { ajv } from "../validation.js";

import * as modelsDev from "./_models_dev.js";

const API = modelsDev.API;
const FILE = "avp_prices.json";

export interface ModelPrice {
  readonly input: number;
  readonly output: number;
  readonly cache_read?: number | null;
  readonly cache_write?: number | null;
}
export interface Prices extends modelsDev.Snapshot {
  readonly models: Record<string, ModelPrice>;
}
const number = { type: "number", minimum: 0 };
const validatePrices = ajv.compile({
  type: "object",
  additionalProperties: false,
  required: ["source", "fetched", "models"],
  properties: {
    source: { type: "string" },
    fetched: { type: "string", format: "date-time" },
    models: {
      type: "object",
      additionalProperties: {
        type: "object",
        additionalProperties: false,
        required: ["input", "output"],
        properties: {
          input: number,
          output: number,
          cache_read: { anyOf: [number, { type: "null" }] },
          cache_write: { anyOf: [number, { type: "null" }] },
        },
      },
    },
  },
});
function parsePrices(value: unknown): Prices {
  const prices = { source: API, ...(value as Record<string, unknown>) };
  if (!validatePrices(prices))
    throw new TypeError(ajv.errorsText(validatePrices.errors));
  return prices as unknown as Prices;
}
let bundled: Prices | undefined;
export function bundledPrices(): Prices {
  return (bundled ??= modelsDev.bundled(FILE, parsePrices));
}
export function defaultCachePath(): string {
  return modelsDev.cachePath(FILE);
}

export async function fetchPrices(
  catalog?: Record<string, unknown>,
): Promise<Prices> {
  catalog = await modelsDev.fetchCatalog(catalog);
  const models: Record<string, ModelPrice> = {};
  for (const [providerId, value] of Object.entries(catalog)) {
    const provider = value as {
      models?: Record<string, { cost?: Record<string, number | null> | null }>;
    };
    for (const [modelId, model] of Object.entries(provider.models ?? {})) {
      const cost = model.cost;
      if (cost?.input == null || cost.output == null) continue;
      models[`${providerId}/${modelId}`] = {
        input: cost.input,
        output: cost.output,
        ...(cost.cache_read == null ? {} : { cache_read: cost.cache_read }),
        ...(cost.cache_write == null ? {} : { cache_write: cost.cache_write }),
      };
    }
  }
  return parsePrices({
    source: API,
    fetched: new Date().toISOString(),
    models: Object.fromEntries(
      Object.keys(models)
        .sort()
        .map((id) => [id, models[id]]),
    ),
  });
}

export async function savePrices(
  prices: Prices,
  path = defaultCachePath(),
): Promise<string> {
  return modelsDev.save(prices, path);
}

export function loadPrices(
  path?: string,
  { maxAgeMs }: { maxAgeMs?: number } = {},
): Promise<Prices> {
  return modelsDev.load(path, {
    defaultPath: defaultCachePath(),
    maxAgeMs,
    parse: parsePrices,
    bundled: bundledPrices,
    fetch: () => fetchPrices(),
  });
}

export function findPrice(
  prices: Prices,
  model: ModelRef,
  responseModel?: string | null,
): ModelPrice | undefined {
  for (const id of [responseModel, model.id]) {
    if (id && Object.hasOwn(prices.models, `${model.provider}/${id}`))
      return prices.models[`${model.provider}/${id}`];
  }
}
export interface CostOptions {
  inputTokens: number;
  outputTokens: number;
  cacheReadInputTokens?: number;
  cacheCreationInputTokens?: number;
  responseModel?: string | null;
  reportedCostUsd?: number | null;
}
export function computeCost(
  prices: Prices,
  model: ModelRef,
  options: CostOptions,
): [number, CostSource] {
  if (options.reportedCostUsd != null)
    return [options.reportedCostUsd, "reported"];
  const price = findPrice(prices, model, options.responseModel);
  if (!price) return [0, "unknown"];
  const read = options.cacheReadInputTokens ?? 0;
  const write = options.cacheCreationInputTokens ?? 0;
  const uncached = options.inputTokens - read - write;
  if (uncached < 0)
    throw new RangeError("cache read and creation tokens exceed input_tokens");
  return [
    (uncached * price.input +
      read * (price.cache_read ?? price.input) +
      write * (price.cache_write ?? price.input) +
      options.outputTokens * price.output) /
      1_000_000,
    "computed",
  ];
}
