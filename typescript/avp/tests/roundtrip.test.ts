/**
 * Round-trip smoke for the generated TypeScript types.
 *
 * Pins that real AVP events the Python agent emits structurally match the
 * generated types — type-checked at compile time AND structurally at runtime
 * via JSON.parse. If the schema bumps and a field gets renamed, this test
 * stops compiling.
 *
 * Uses Node's built-in test agent (no jest/vitest dep — keeps the package
 * dev-deps to just `typescript`).
 */
import { strict as assert } from "node:assert";
import { test } from "node:test";

import type { Event } from "../src/index.js";
import type {
  AgentStartedEvent,
  ModelTurnEndedEvent,
  RefusalRecordedEvent,
} from "../src/trajectory.js";

test("agent_started parses + matches the discriminator", () => {
  const raw = `{
    "specversion": "1.0",
    "id": "5c390872-f1e6-4e1d-9638-b2edb74ed074",
    "time": "2026-05-07T14:49:42.327551+00:00",
    "subject": "r1",
    "datacontenttype": "application/json",
    "type": "avp.agent_started",
    "source": "avp://agent",
    "data": {
      "trace_id": "00000000000000000000000000000000",
      "span_id": "0000000000000000",
      "parent_span_id": "0000000000000000",
      "gen_ai.operation.name": "invoke_agent",
      "avp.schema_version": "0.1",
      "avp.commission": {
        "schema_version": "0.1",
        "run_id": "r1",
        "model": "test/mock"
      },
      "started_at": "2026-05-08T00:00:00+00:00"
    }
  }`;

  const ev = JSON.parse(raw) as Event;
  assert.equal(ev.type, "avp.agent_started");

  // Type-narrowing: discriminator-based, same way consumers would do it.
  if (ev.type === "avp.agent_started") {
    const started: AgentStartedEvent = ev;
    assert.equal(started.subject, "r1");
    assert.equal(started.source, "avp://agent");
  }
});

test("model_turn_ended carries avp.cost.source provenance tag", () => {
  const raw = `{
    "specversion": "1.0",
    "id": "test-id",
    "time": "2026-05-07T00:00:00Z",
    "subject": "r1",
    "datacontenttype": "application/json",
    "type": "avp.model_turn_ended",
    "source": "avp://agent",
    "data": {
      "trace_id": "00000000000000000000000000000000",
      "span_id": "1111111111111111",
      "parent_span_id": "0000000000000000",
      "step": 1,
      "duration_ms": 42,
      "gen_ai.usage.input_tokens": 100,
      "gen_ai.usage.output_tokens": 25,
      "avp.cost_usd": 0.001,
      "avp.cost.source": "computed"
    }
  }`;
  const ev = JSON.parse(raw) as Event;
  if (ev.type === "avp.model_turn_ended") {
    const turn: ModelTurnEndedEvent = ev;
    // Field accessor proves the dotted alias is mapped correctly in the types.
    assert.equal(turn.data["avp.cost.source"], "computed");
    assert.equal(turn.data["avp.cost_usd"], 0.001);
  } else {
    assert.fail(`expected model_turn_ended, got ${ev.type}`);
  }
});

test("refusal_recorded parses with provider tag", () => {
  const raw = `{
    "specversion": "1.0",
    "id": "test-id",
    "time": "2026-05-07T00:00:00Z",
    "subject": "r1",
    "datacontenttype": "application/json",
    "type": "avp.refusal_recorded",
    "source": "avp://agent",
    "data": {
      "trace_id": "00000000000000000000000000000000",
      "span_id": "2222222222222222",
      "parent_span_id": "0000000000000000",
      "step": 1,
      "avp.refusal.reason": "refusal",
      "avp.refusal.provider": "anthropic"
    }
  }`;
  const ev = JSON.parse(raw) as Event;
  if (ev.type === "avp.refusal_recorded") {
    const r: RefusalRecordedEvent = ev;
    assert.equal(r.data["avp.refusal.reason"], "refusal");
    assert.equal(r.data["avp.refusal.provider"], "anthropic");
  } else {
    assert.fail(`expected refusal_recorded, got ${ev.type}`);
  }
});
