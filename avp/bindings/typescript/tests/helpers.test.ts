/**
 * Pricing, ids, and sinks: the helpers the Recorder is built on.
 */
import { strict as assert } from "node:assert";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { newEventId, newSpanId, newTraceId } from "../src/ids.js";
import { computeCost, loadDefaultPrices } from "../src/pricing.js";
import { Recorder } from "../src/recorder.js";
import { FileSink } from "../src/sink.js";

test("bundled price table loads from the Python package", () => {
  const prices = loadDefaultPrices();
  const opus = prices["anthropic/claude-opus-4-7"];
  assert.ok(opus, "opus 4.7 in default table");
  assert.equal(opus.input, 5);
  assert.equal(opus.output, 25);
});

test("cost splits cache reads and writes from fresh input", () => {
  // fresh = 1000 - 200 - 100 = 700.
  // 700*5 + 200*0.5 + 100*6.25 + 500*25 = 16725 per 1e6.
  const [cost, source] = computeCost(
    "anthropic",
    "claude-opus-4-7",
    1000,
    500,
    200,
    100,
    loadDefaultPrices(),
  );
  assert.equal(source, "computed");
  assert.ok(Math.abs(cost - 0.016725) < 1e-12, `${cost}`);
  assert.deepEqual(computeCost("anthropic", "no-such-model", 10, 10, 0, 0, {}), [0, "unknown"]);
});

test("ids are W3C hex and unique", () => {
  assert.match(newTraceId(), /^[0-9a-f]{32}$/);
  assert.match(newSpanId(), /^[0-9a-f]{16}$/);
  assert.notEqual(newEventId(), newEventId());
});

test("FileSink truncates, then writes one NDJSON line per event", () => {
  const path = join(mkdtempSync(join(tmpdir(), "avp-ts-")), "out.ndjson");
  writeFileSync(path, "stale\n");
  const sink = new FileSink(path);
  const rec = new Recorder(sink, { runId: "r1" });
  rec.start();
  rec.stop("converged");
  sink.close();
  const lines = readFileSync(path, "utf8").trimEnd().split("\n");
  assert.deepEqual(
    lines.map((l) => JSON.parse(l).type),
    ["avp.agent_started", "avp.agent_stopped"],
  );
  assert.ok(lines.every((l) => JSON.parse(l).subject === "r1"));
});
