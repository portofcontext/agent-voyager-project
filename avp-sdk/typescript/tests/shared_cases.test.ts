import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import { Recorder, RecorderError } from "../src/recorder.js";
import { parseCommission } from "../src/commission.js";
import { parseDescriptor } from "../src/descriptor.js";
import { finalOutput, type Recording } from "../src/trajectory.js";
import { checkCommission } from "../src/utils/preflight.js";
import { planRun } from "../src/utils/run_plan.js";

const cases = new URL("../../../testdata/", import.meta.url);
const start = Date.parse("2026-01-01T00:00:00Z");
function same(actual: unknown, expected: unknown): void {
  if (expected === "<any>") {
    assert.equal(typeof actual, "string");
    return;
  }
  if (typeof actual === "number" && typeof expected === "number") {
    assert.ok(
      Math.abs(actual - expected) <=
        Math.max(1e-12, 1e-9 * Math.max(Math.abs(actual), Math.abs(expected))),
    );
  } else if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual));
    assert.equal(actual.length, expected.length);
    actual.forEach((value, i) => same(value, expected[i]));
  } else if (expected && typeof expected === "object") {
    assert.ok(actual && typeof actual === "object");
    assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort());
    for (const [key, value] of Object.entries(expected))
      same((actual as Record<string, unknown>)[key], value);
  } else if (typeof expected === "string" && expected.startsWith("2026-01-01T"))
    assert.equal(Date.parse(String(actual)), Date.parse(expected));
  else if (
    typeof expected === "string" &&
    expected.startsWith("{") &&
    typeof actual === "string"
  )
    same(JSON.parse(actual), JSON.parse(expected));
  else assert.deepEqual(actual, expected);
}
async function call(rec: Recorder, c: Record<string, any>): Promise<void> {
  switch (c.call) {
    case "begin":
      await rec.begin(c.received, parseDescriptor(c.descriptor));
      break;
    case "start":
      await rec.start(c.agent, c.prompt, { systemPrompt: c.system_prompt });
      break;
    case "step":
      await rec.step(c.parts, {
        usage: c.usage,
        modelName: c.model_name,
        finishReasons: c.finish_reasons,
        subagent: c.subagent,
      });
      break;
    case "result":
      await rec.result(c.call_id, c.content, {
        isError: c.is_error,
        structuredContent: c.structured_content,
      });
      break;
    case "subagent_started":
      await rec.subagentStarted(c.call_id, c.name, c.prompt);
      break;
    case "subagent_stopped":
      await rec.subagentStopped(c.call_id, c.reason, {
        usage: c.usage,
        modelName: c.model_name,
      });
      break;
    case "error":
      await rec.error(c.code, c.message, { subagent: c.subagent });
      break;
    case "stop":
      await rec.stop(c.reason, c.output);
      break;
    default:
      throw new Error(`unknown call ${c.call}`);
  }
}
for (const name of readdirSync(new URL("recorder/", cases)).filter((name) =>
  name.endsWith(".json"),
)) {
  test(`Recorder: ${name}`, async () => {
    const vector = JSON.parse(
      readFileSync(new URL(`recorder/${name}`, cases), "utf8"),
    );
    const events: Recording[] = [];
    let clock = start;
    let id = 0;
    const rec = new Recorder(
      async (event) => {
        events.push(event);
      },
      {
        runId: "run-0",
        prices: {
          source: "https://models.dev/api.json",
          fetched: new Date(start).toISOString(),
          models: vector.prices ?? {},
        },
        now: () => new Date(clock),
        newId: () => `event-${++id}`,
      },
    );
    for (const command of vector.calls) {
      clock = start + command.t;
      const written = events.length;
      if (command.raises) {
        await assert.rejects(call(rec, command), RecorderError);
        assert.equal(events.length, written);
      } else await call(rec, command);
    }
    same(events.at(-1)!.trajectory, vector.trajectory);
    assert.equal(events.length, 1);
    assert.deepEqual(
      [...events[0].assets.keys()].sort(),
      (vector.files ?? []).sort(),
    );
    const stop = [...vector.calls].reverse().find((c) => c.call === "stop");
    if (stop && vector.calls.some((c: any) => c.call === "start" && !c.raises))
      assert.deepEqual(
        finalOutput(events.at(-1)!.trajectory),
        stop.output ?? null,
      );
  });
}
for (const name of readdirSync(new URL("run_plan/", cases)).filter((name) =>
  name.endsWith(".json"),
)) {
  test(`Run plan: ${name}`, () => {
    const vector = JSON.parse(
      readFileSync(new URL(`run_plan/${name}`, cases), "utf8"),
    );
    const commission = parseCommission(vector.commission);
    const descriptor = parseDescriptor(vector.descriptor);
    assert.equal(checkCommission(commission, descriptor), undefined);
    same(
      JSON.parse(JSON.stringify(planRun(commission, descriptor))),
      vector.plan,
    );
  });
}
