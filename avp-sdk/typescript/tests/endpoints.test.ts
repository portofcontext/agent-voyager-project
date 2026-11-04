import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  BEARER,
  bundledEndpoints,
  defaultBaseUrl,
  fetchEndpoints,
  loadEndpoints,
  providerAuth,
  saveEndpoints,
  type Endpoints,
} from "../src/utils/endpoints.js";

test("catalog conversion follows the shared Python cases", async (t) => {
  t.mock.method(globalThis, "fetch", async () => {
    throw new Error("unexpected fetch");
  });
  const cases = JSON.parse(
    await readFile(
      new URL("../../../testdata/endpoints/catalog.json", import.meta.url),
      "utf8",
    ),
  );
  for (const item of cases) {
    const endpoints = await fetchEndpoints(item.catalog, item);
    assert.deepEqual(endpoints.providers, item.providers, item.name);
  }
});

test("bundled defaults cover API-key schemes without guessing dynamic authentication", () => {
  const shipped = bundledEndpoints();
  assert.equal(
    defaultBaseUrl(shipped, "anthropic"),
    "https://api.anthropic.com/v1",
  );
  assert.equal(
    defaultBaseUrl(shipped, "openrouter"),
    "https://openrouter.ai/api/v1",
  );
  assert.equal(defaultBaseUrl(shipped, "amazon-bedrock"), undefined);
  assert.deepEqual(providerAuth(shipped, "anthropic"), {
    header: "x-api-key",
    prefix: "",
  });
  assert.deepEqual(providerAuth(shipped, "google"), {
    header: "x-goog-api-key",
    prefix: "",
  });
  assert.deepEqual(providerAuth(shipped, "openrouter"), BEARER);
  assert.deepEqual(providerAuth(shipped, "amazon-bedrock"), BEARER);
  for (const provider of [
    "google-vertex",
    "unknown",
    "toString",
    "__proto__",
  ]) {
    assert.equal(providerAuth(shipped, provider), undefined);
    assert.equal(defaultBaseUrl(shipped, provider), undefined);
  }
});

test("endpoint caches round-trip and refresh only with maxAgeMs", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "avp-endpoints-"));
  const path = join(dir, "nested/endpoints.json");
  let fetches = 0;
  t.mock.method(globalThis, "fetch", async () => {
    fetches++;
    return new Response(
      JSON.stringify({
        test: { api: "https://test.example/v1", npm: "@ai-sdk/anthropic" },
      }),
    );
  });
  try {
    await assert.rejects(loadEndpoints(path), { code: "ENOENT" });
    assert.equal(fetches, 0);
    const fresh = await loadEndpoints(path, { maxAgeMs: 86_400_000 });
    assert.equal(fetches, 1);
    assert.equal(defaultBaseUrl(fresh, "test"), "https://test.example/v1");
    assert.deepEqual(providerAuth(fresh, "test"), {
      header: "x-api-key",
      prefix: "",
    });
    assert.deepEqual(await loadEndpoints(path), fresh);
    const stale = {
      ...fresh,
      fetched: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    };
    await saveEndpoints(stale, path);
    assert.deepEqual(await loadEndpoints(path), stale);
    assert.deepEqual(
      await loadEndpoints(path, { maxAgeMs: 3 * 86_400_000 }),
      stale,
    );
    assert.equal(fetches, 1);
    await loadEndpoints(path, { maxAgeMs: 86_400_000 });
    assert.equal(fetches, 2);
    await writeFile(path, "broken JSON");
    await assert.rejects(loadEndpoints(path, { maxAgeMs: 0 }), SyntaxError);
    assert.equal(fetches, 2);
  } finally {
    await rm(dir, { recursive: true });
  }
});

test("offline default loading selects the newer bundled or cached endpoints", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "avp-endpoints-"));
  const old = process.env.XDG_CACHE_HOME;
  process.env.XDG_CACHE_HOME = dir;
  t.mock.method(globalThis, "fetch", async () => {
    throw new Error("unexpected fetch");
  });
  try {
    const shipped = bundledEndpoints();
    assert.deepEqual(await loadEndpoints(), shipped);
    const cached: Endpoints = {
      source: shipped.source,
      fetched: new Date(Date.parse(shipped.fetched) - 86_400_000).toISOString(),
      providers: {},
    };
    await saveEndpoints(cached);
    assert.deepEqual(await loadEndpoints(), shipped);
    const newer = {
      ...cached,
      fetched: new Date(Date.parse(shipped.fetched) + 86_400_000).toISOString(),
    };
    const path = await saveEndpoints(newer);
    assert.deepEqual(await loadEndpoints(), newer);
    await writeFile(
      path,
      JSON.stringify({
        ...newer,
        providers: { test: { auth: { header: "x-key" } } },
      }),
    );
    assert.deepEqual(providerAuth(await loadEndpoints(), "test"), {
      header: "x-key",
      prefix: "",
    });
    for (const endpoint of [
      { extra: true },
      { auth: { prefix: "Bearer " } },
      { auth: { header: 1 } },
    ]) {
      await writeFile(
        path,
        JSON.stringify({ ...newer, providers: { test: endpoint } }),
      );
      await assert.rejects(loadEndpoints(), TypeError);
    }
  } finally {
    if (old === undefined) delete process.env.XDG_CACHE_HOME;
    else process.env.XDG_CACHE_HOME = old;
    await rm(dir, { recursive: true });
  }
});
