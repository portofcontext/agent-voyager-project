import assert from "node:assert/strict";
import test from "node:test";
import { parseCommission } from "../src/commission.js";
import { parseDescriptor } from "../src/descriptor.js";
import { Recorder, type UsageReport } from "../src/recorder.js";
import { parseTrajectoryEvent, type Event } from "../src/trajectory.js";

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
  const returned = parseTrajectoryEvent({
    avp_version: "0.1",
    id: "e",
    run_id: "r",
    time: "2026-01-01T00:00:00Z",
    type: "tool_returned",
    data: {
      tool_call_id: "t",
      tool_name: "read",
      duration_ms: 0,
      tool_result: {
        type: "tool_result",
        tool_use_id: "t",
        content: [
          {
            type: "text",
            text: "x",
            citations: null,
            provider_field: null,
            _meta: { x: null },
          },
        ],
      },
    },
  });
  assert.deepEqual(
    returned?.type === "tool_returned" && returned.data.tool_result.content,
    [{ type: "text", text: "x", _meta: { x: null } }],
  );
});
test("known events validate their shape, while future event types are skipped", () => {
  const event = {
    avp_version: "0.1",
    id: "e",
    run_id: "r",
    time: "2026-01-01T00:00:00Z",
    type: "assistant_message",
    data: {
      model: { provider: "p", id: "m" },
      duration_ms: 0,
      content: [{ type: "text", text: "Hi", provider_field: { x: true } }],
      usage: {
        input_tokens: 1,
        output_tokens: 2,
        cost_usd: 0,
        cost_source: "unknown",
      },
    },
  };
  assert.deepEqual(parseTrajectoryEvent(JSON.stringify(event)), event);
  assert.deepEqual(
    parseTrajectoryEvent(Buffer.from(JSON.stringify(event))),
    event,
  );
  for (const time of [
    "2026-01-01",
    "2026-01-01 00:00:00Z",
    "2026-01-01T00:00:00",
    "2026-02-30T00:00:00Z",
  ])
    assert.throws(() => parseTrajectoryEvent({ ...event, time }), TypeError);
  assert.throws(
    () =>
      parseTrajectoryEvent({
        ...event,
        data: { ...event.data, duration_ms: -1 },
      }),
    TypeError,
  );
  assert.throws(
    () =>
      parseTrajectoryEvent({
        ...event,
        data: { ...event.data, usage: { ...event.data.usage, cost_usd: -1 } },
      }),
    TypeError,
  );
  for (const type of ["future_event", "constructor", "toString", "__proto__"])
    assert.equal(parseTrajectoryEvent({ type }), undefined);
  assert.throws(
    () => parseTrajectoryEvent({ type: "agent_started" }),
    TypeError,
  );
  const error = parseTrajectoryEvent({
    avp_version: "0.1",
    id: "e",
    run_id: "r",
    time: event.time,
    type: "error_occurred",
    data: { error_code: "future_code", error_message: "new failure" },
  });
  assert.equal(
    error?.type === "error_occurred" && error.data.error_code,
    "unknown",
  );
});
test("Recorder omits empty response metadata and rejects invalid usage without emitting events", async () => {
  const events: Event[] = [];
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
  assert.ok(!Object.hasOwn(events[1], "meta"));
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
  await rec.subagentInvoked("s", "helper", undefined, {
    subagentInvocationId: "",
  });
  assert.equal(
    events[2].type === "subagent_invoked" &&
      events[2].data.subagent_invocation_id,
    "",
  );
});
