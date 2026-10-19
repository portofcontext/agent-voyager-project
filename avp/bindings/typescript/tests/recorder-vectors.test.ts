/**
 * Run the shared recorder vectors against the TypeScript `Recorder`. Contract:
 * `avp/core/conformance/src/avp_conformance/recorder/v0.1/README.md`.
 */
import { strict as assert } from "node:assert";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { Recorder, RecorderError, type Clock, type Ids } from "../src/recorder.js";
import { MemorySink } from "../src/sink.js";

const TRACE_ID = "0af7651916cd43dd8448eb211c80319c";
const EPOCH_MS = Date.parse("2026-01-01T00:00:00.000Z");
const VECTORS = (() => {
  // Walk up from this file (tests/ or the compiled dist-test/tests/) to avp/.
  let dir = dirname(fileURLToPath(import.meta.url));
  for (;;) {
    const candidate = join(dir, "core", "conformance", "src", "avp_conformance", "recorder", "v0.1");
    if (existsSync(candidate)) return candidate + "/";
    if (dirname(dir) === dir) throw new Error("recorder vectors not found");
    dir = dirname(dir);
  }
})();

type Json = Record<string, any>;

class VectorClock implements Clock {
  t = 0;
  nowIso(): string {
    return new Date(EPOCH_MS + this.t).toISOString();
  }
  monotonic(): number {
    return this.t / 1000;
  }
}

class VectorIds implements Ids {
  private spans = 0;
  private events = 0;
  traceId(): string {
    return TRACE_ID;
  }
  spanId(): string {
    return (++this.spans).toString(16).padStart(16, "0");
  }
  eventId(): string {
    return `evt-${++this.events}`;
  }
}

function apply(rec: Recorder, a: Json): void {
  switch (a.op) {
    case "prelude":
      return rec.prelude(a.commission, a.descriptor);
    case "start":
      return rec.start({
        requestModel: a.request_model,
        prompt: a.prompt,
        systemPrompt: a.system_prompt,
        tools: a.tools,
        mcpServers: a.mcp_servers,
        skills: a.skills,
        subagents: a.subagents,
        sessionId: a.session_id,
        threadId: a.thread_id,
        tags: a.tags,
        meta: a.meta,
      });
    case "assistant":
      return rec.assistant(a.content, a.usage, {
        model: a.model,
        requestModel: a.request_model,
        turnKey: a.turn_key,
        finishReasons: a.finish_reasons,
        meta: a.meta,
        costUsd: a.cost_usd,
        durationMs: a.duration_ms,
      });
    case "usage":
      return rec.usage(a.usage, {
        turnKey: a.turn_key,
        costUsd: a.cost_usd,
        durationMs: a.duration_ms,
      });
    case "close_turn":
      return rec.closeTurn();
    case "tool_result":
      return rec.toolResult(a.call_id, a.content, {
        isError: a.is_error,
        structuredContent: a.structured_content,
      });
    case "subagent_start":
      return rec.subagentStart(a.invocation_id, a.name, {
        input: a.input,
        description: a.description,
      });
    case "subagent_result":
      return rec.subagentResult(a.invocation_id, a.text, {
        reason: a.reason,
        usage: a.usage,
        structured: a.structured,
      });
    case "error":
      return rec.error(a.code, a.message);
    case "stop":
      return rec.stop(a.reason, a.output);
    default:
      throw new Error(`unknown recorder op ${a.op}`);
  }
}

/** Rename event ids and span ids by order of first appearance on the wire. */
function normalize(events: Json[]): Json[] {
  const names = new Map<string, string>();
  const counts: Record<string, number> = {};
  const name = (v: string, prefix: string): string => {
    if (v === "0000000000000000") return v;
    if (!names.has(v)) {
      counts[prefix] = (counts[prefix] ?? 0) + 1;
      names.set(v, `${prefix}-${counts[prefix]}`);
    }
    return names.get(v)!;
  };
  return events.map((e) => {
    const out = JSON.parse(JSON.stringify(e));
    out.id = name(out.id, "evt");
    out.data.span_id = name(out.data.span_id, "span");
    out.data.parent_span_id = name(out.data.parent_span_id, "span");
    return out;
  });
}

function same(got: unknown, want: unknown, path: string): void {
  if (typeof got === "number" && typeof want === "number") {
    assert.ok(Math.abs(got - want) <= 1e-12, `${path}: ${got} != ${want}`);
    return;
  }
  if (Array.isArray(got) && Array.isArray(want) && got.length === want.length) {
    got.forEach((g, i) => same(g, want[i], `${path}[${i}]`));
    return;
  }
  if (
    got && want && typeof got === "object" && typeof want === "object" &&
    !Array.isArray(got) && !Array.isArray(want)
  ) {
    const keys = new Set([...Object.keys(got), ...Object.keys(want)]);
    for (const k of [...keys].sort()) {
      const [g, w] = [(got as Json)[k], (want as Json)[k]];
      assert.ok(g !== undefined && w !== undefined, `${path}.${k}: got ${JSON.stringify(g)}, want ${JSON.stringify(w)}`);
      same(g, w, `${path}.${k}`);
    }
    return;
  }
  assert.deepEqual(got, want, `${path}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
}

function run(vector: Json): Json[] {
  const cfg = vector.recorder ?? {};
  const clock = new VectorClock();
  const sink = new MemorySink();
  const rec = new Recorder(sink, {
    runId: cfg.run_id,
    provider: cfg.provider,
    prices: cfg.prices,
    clock,
    ids: new VectorIds(),
  });
  for (const call of vector.calls as Json[]) {
    clock.t = call.t;
    const before = sink.events.length;
    if (call.expect_error !== undefined) {
      assert.throws(
        () => apply(rec, call),
        (err: unknown) => err instanceof RecorderError && err.message === call.expect_error,
        `${vector.name}: expected RecorderError ${JSON.stringify(call.expect_error)}`,
      );
      assert.equal(sink.events.length, before, "rejected reports must not emit");
    } else {
      apply(rec, call);
    }
  }
  // Serialize as the NDJSON line would be.
  return normalize(JSON.parse(JSON.stringify(sink.events)));
}

const paths = readdirSync(VECTORS).filter((f) => f.endsWith(".json")).sort();

test("found the shared vectors", () => {
  assert.ok(paths.length >= 10, `expected the shared vectors, found ${paths.length}`);
});

for (const file of paths) {
  const vector = JSON.parse(readFileSync(VECTORS + file, "utf8")) as Json;
  test(`recorder vector: ${vector.name}`, () => {
    const got = run(vector);
    const want = vector.expected as Json[];
    assert.deepEqual(got.map((e) => e.type), want.map((e) => e.type), "event types");
    got.forEach((g, i) => same(g, want[i], `event[${i}]`));
  });
}
