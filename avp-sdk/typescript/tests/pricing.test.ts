import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  bundledPrices,
  computeCost,
  fetchPrices,
  loadPrices,
  savePrices,
  type Prices,
} from "../src/utils/pricing.js";

function table(): Prices {
  return {
    source: "https://models.dev/api.json",
    fetched: new Date().toISOString(),
    models: {
      "p/m": { input: 3, output: 15, cache_read: 0.3, cache_write: 3.75 },
      "p/dated": { input: 1, output: 1 },
      "p/plain": { input: 2, output: 8 },
    },
  };
}

test("costs use the provider, response model, and cache rates", () => {
  const prices = table();
  const metrics = {
    prompt_tokens: 3_000_000,
    completion_tokens: 0,
    cached_tokens: 1_000_000,
    extra: { avp: { cache_creation_input_tokens: 1_000_000 } },
  };
  assert.equal(computeCost(prices, "p", "m", metrics), 7.05);
  assert.equal(computeCost(prices, "other", "m", metrics), undefined);
  assert.equal(computeCost(prices, "p", "dated", metrics), 3);
  assert.equal(computeCost(prices, "p", "missing", metrics), undefined);
  assert.equal(computeCost(prices, "p", "plain", metrics), 6);
  assert.equal(computeCost(prices, "p", "m", {}), undefined);
  assert.throws(
    () =>
      computeCost(prices, "p", "m", {
        prompt_tokens: 0,
        completion_tokens: 0,
        cached_tokens: 1,
      }),
    /exceed prompt_tokens/,
  );
});

test("snapshots round-trip, refresh only with maxAgeMs, and reject corrupt caches", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "avp-prices-"));
  const path = join(dir, "nested/prices.json");
  const prices = table();
  let fetches = 0;
  t.mock.method(globalThis, "fetch", async () => {
    fetches++;
    return new Response(
      JSON.stringify({
        p: { models: { m: { cost: { input: 3, output: 15 } } } },
      }),
    );
  });
  try {
    await assert.rejects(loadPrices(path), { code: "ENOENT" });
    assert.equal(fetches, 0);
    const fresh = await loadPrices(path, { maxAgeMs: 86_400_000 });
    assert.equal(fetches, 1);
    assert.equal(fresh.models["p/m"].input, 3);
    assert.deepEqual(await loadPrices(path), fresh);
    assert.equal(fetches, 1);
    const stale = {
      ...prices,
      fetched: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    };
    await savePrices(stale, path);
    assert.deepEqual(
      await loadPrices(path, { maxAgeMs: 3 * 86_400_000 }),
      stale,
    );
    await loadPrices(path, { maxAgeMs: 86_400_000 });
    assert.equal(fetches, 2);
    await writeFile(path, "not JSON");
    await assert.rejects(loadPrices(path, { maxAgeMs: 0 }), SyntaxError);
    assert.equal(fetches, 2);
  } finally {
    await rm(dir, { recursive: true });
  }
});

test("default loading selects the newer bundled or cached snapshot without networking", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "avp-prices-"));
  const old = process.env.XDG_CACHE_HOME;
  process.env.XDG_CACHE_HOME = dir;
  t.mock.method(globalThis, "fetch", async () => {
    throw new Error("unexpected fetch");
  });
  try {
    const shipped = bundledPrices();
    assert.ok(shipped.models["anthropic/claude-sonnet-4-5"].output > 0);
    assert.deepEqual(await loadPrices(), shipped);
    await savePrices({
      ...table(),
      fetched: new Date(Date.parse(shipped.fetched) - 86_400_000).toISOString(),
    });
    assert.deepEqual(await loadPrices(), shipped);
    const newer = {
      ...table(),
      fetched: new Date(Date.parse(shipped.fetched) + 86_400_000).toISOString(),
    };
    const path = await savePrices(newer);
    assert.deepEqual(await loadPrices(), newer);
    assert.deepEqual(JSON.parse(await readFile(path, "utf8")), newer);
    await writeFile(
      path,
      JSON.stringify({ ...newer, models: { "p/m": { input: -1, output: 0 } } }),
    );
    await assert.rejects(loadPrices(), TypeError);
  } finally {
    if (old === undefined) delete process.env.XDG_CACHE_HOME;
    else process.env.XDG_CACHE_HOME = old;
    await rm(dir, { recursive: true });
  }
});

test("catalog conversion keeps priced models and zero prices without fetching", async (t) => {
  t.mock.method(globalThis, "fetch", async () => {
    throw new Error("unexpected fetch");
  });
  const prices = await fetchPrices({
    p: {
      models: {
        free: { cost: { input: 0, output: 0 } },
        partial: { cost: { input: 3 } },
        unpriced: {},
        cached: { cost: { input: 2, output: 8, cache_read: 0.5, extra: 12 } },
      },
    },
  });
  assert.deepEqual(Object.keys(prices.models), ["p/cached", "p/free"]);
  assert.deepEqual(prices.models["p/cached"], {
    input: 2,
    output: 8,
    cache_read: 0.5,
  });
});
