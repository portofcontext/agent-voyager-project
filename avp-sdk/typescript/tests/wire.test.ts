import assert from "node:assert/strict";
import test from "node:test";
import { parseCommission } from "../src/commission.js";
import { parseDescriptor } from "../src/descriptor.js";
import { Recorder, type UsageReport } from "../src/recorder.js";
import { parseTrajectory, type Recording } from "../src/trajectory.js";

const commission = () => ({
  avp_version: "0.1",
  run_id: "r",
  prompt: "Hi",
  model: { provider: "p", id: "m" },
});
test("Commission validation enforces schema constraints", () => {
  for (const fields of [
    { extra: 1 },
    { avp_version: "0.2" },
    { model: { provider: "Invalid/provider", id: "m" } },
    { agents: { "Bad Name": {} } },
    { output_schema: { type: "array" } },
    { mcp_servers: [{ id: "s", type: "stdio", command: [] }] },
    {
      mcp_servers: [
        {
          id: "s",
          type: "stdio",
          command: ["echo"],
          env: { KEY: { proxy: "key" } },
        },
      ],
    },
    { skills: [{ name: "lint", files: {} }] },
    { skills: [{ name: "lint", files: { "SKILL.md": 7 } }] },
  ])
    assert.throws(
      () => parseCommission({ ...commission(), ...fields }),
      TypeError,
      JSON.stringify(fields),
    );
});
test("open wire objects retain provider extensions and arbitrary JSON nulls", () => {
  const descriptor = {
    avp_version: "0.1",
    agent_name: "demo",
    agent_version: "1",
    tools: [
      {
        name: "read",
        title: "Read",
        inputSchema: {
          type: "object",
          properties: { path: { type: "string" } },
        },
        annotations: { readOnlyHint: true },
        _meta: { value: null },
      },
    ],
    skills: [
      { name: "review", description: "Review", metadata: { version: "1" } },
    ],
  };
  assert.deepEqual(parseDescriptor(descriptor), descriptor);
  assert.throws(
    () =>
      parseDescriptor({
        ...descriptor,
        tools: [{ name: "bad", inputSchema: {} }],
      }),
    TypeError,
  );
});
test("external ATIF needs no AVP extensions and rejects broken call references", () => {
  const value = {
    schema_version: "ATIF-v1.8",
    agent: { name: "external", version: "1" },
    steps: [
      {
        step_id: 1,
        source: "agent",
        message: "ok",
        tool_calls: [
          { tool_call_id: "c", function_name: "echo", arguments: {} },
        ],
        observation: { results: [{ source_call_id: "c", content: "ok" }] },
      },
    ],
  };
  assert.deepEqual(parseTrajectory(value), value);
  value.steps[0].observation.results[0].source_call_id = "missing";
  assert.throws(() => parseTrajectory(value), /unmatched/);
});
test("Recorder omits empty response metadata and rejects invalid usage without emitting events", async () => {
  const events: Recording[] = [];
  let nextId = 0;
  const rec = new Recorder(
    async (event) => {
      events.push(event);
    },
    { runId: "", newId: () => `id-${++nextId}` },
  );
  assert.equal(rec.runId, "id-1");
  await rec.start({ prompt: "Hi", model: { provider: "p", id: "m" } });
  await rec.response([{ type: "text", text: "Hi" }], { meta: {} });
  assert.ok(
    !Object.hasOwn(
      events[1].trajectory.steps[1].extra?.avp ?? {},
      "annotations",
    ),
  );
  for (const usage of [
    { input_tokens: -1, output_tokens: 0 },
    { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 1 },
    { input_tokens: 0, output_tokens: 0, cost_source: "reported" },
  ] as UsageReport[]) {
    await assert.rejects(
      rec.response([{ type: "text", text: "Bad" }], { usage }),
    );
    assert.equal(events.length, 2);
  }
  await assert.rejects(
    rec.subagentInvoked("s", "helper", undefined, {
      subagentInvocationId: "missing",
    }),
  );
});

test("upstream semantics match Python reference models", async () => {
  const { readFileSync } = await import("node:fs");
  const cases = JSON.parse(
    readFileSync(
      new URL("../../../testdata/atif/validation.json", import.meta.url),
      "utf8",
    ),
  );
  const external = JSON.parse(
    readFileSync(
      new URL("../../../testdata/atif/external-terminus.json", import.meta.url),
      "utf8",
    ),
  );
  assert.equal(parseTrajectory(external).agent.name, external.agent.name);
  for (const item of cases) {
    if (item.valid)
      assert.doesNotThrow(() => parseTrajectory(item.trajectory), item.name);
    else assert.throws(() => parseTrajectory(item.trajectory), item.name);
  }
});
