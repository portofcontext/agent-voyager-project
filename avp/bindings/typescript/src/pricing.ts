/**
 * Shared model pricing for AVP agents.
 *
 * The price table has a single source of truth: `prices.json` in the Python
 * `avp` package (`avp/data/prices.json`, synced from models.dev). Like the
 * Rust crate, this module reads that same file rather than committing a
 * per-language copy, so it resolves the path relative to the repository
 * checkout. Callers may build or override their own `PriceTable`.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** Provenance of a cost number on the wire (`avp.cost.source`). */
export type CostSource = "computed" | "reported" | "unknown";

/** Per-1M-token pricing in USD. */
export interface ModelPrice {
  input: number;
  output: number;
  cache_read?: number;
  cache_write?: number;
}

/** Model key to price. Keys are models.dev `<provider>/<model>` ids. */
export type PriceTable = Record<string, ModelPrice>;

/** `avp/bindings/python/src/avp/data/prices.json`, found from this module (`src/` or a build dir). */
function bundledPrices(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (;;) {
    const candidate = join(dir, "python", "src", "avp", "data", "prices.json");
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) throw new Error("bundled prices.json not found; pass a path");
    dir = parent;
  }
}

/**
 * Load the bundled default price table. Reads on each call and returns a
 * fresh table the caller can mutate. `path` overrides the bundled file.
 */
export function loadDefaultPrices(path?: string | URL): PriceTable {
  const raw = JSON.parse(readFileSync(path ?? bundledPrices(), "utf8")) as {
    models?: PriceTable;
  };
  return raw.models ?? {};
}

/**
 * Resolve a price by the model the agent put on the wire. The exact string is
 * tried first, so a table keyed by bare names works; a bare model is then
 * qualified with `provider` (`claude-sonnet-4-6` under `anthropic`).
 */
export function resolvePrice(
  prices: PriceTable,
  provider: string | null | undefined,
  model: string,
): ModelPrice | undefined {
  if (Object.hasOwn(prices, model)) return prices[model];
  if (provider && !model.includes("/")) {
    const key = `${provider}/${model}`;
    if (Object.hasOwn(prices, key)) return prices[key];
  }
  return undefined;
}

/**
 * Billable USD cost from one turn's token counts, with its provenance.
 * `inputTokens` includes cache reads and writes (the AVP convention); they
 * are billed at their own rates and the fresh remainder at the input rate.
 * An unpriced model returns `[0, "unknown"]`.
 */
export function computeCost(
  provider: string | null | undefined,
  model: string,
  inputTokens: number,
  outputTokens: number,
  cacheRead: number,
  cacheWrite: number,
  prices: PriceTable,
): [number, CostSource] {
  const p = resolvePrice(prices, provider, model);
  if (!p) return [0, "unknown"];
  const fresh = Math.max(0, inputTokens - cacheRead - cacheWrite);
  const cost =
    (fresh * p.input) / 1_000_000 +
    (cacheRead * (p.cache_read ?? 0)) / 1_000_000 +
    (cacheWrite * (p.cache_write ?? 0)) / 1_000_000 +
    (outputTokens * p.output) / 1_000_000;
  return [cost, "computed"];
}
