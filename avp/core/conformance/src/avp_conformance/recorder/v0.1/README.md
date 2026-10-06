# Recorder vectors (v0.1)

Language-neutral test vectors for the `Recorder` each binding ships
(`avp.recorder` in Python, `avp::recorder` in Rust, `recorder` in TypeScript).
A vector is a script of Recorder calls plus the trajectory they must produce.
Every binding runs every vector in its free test tier, so the three native
Recorders cannot drift apart. The conformance cases in `../../cases/` pin what
an agent must put on the wire; these vectors pin how the Recorder gets it there.

## File shape

```json
{
  "name": "plain-turn",
  "description": "what the vector pins",
  "recorder": { "run_id": "run-1", "provider": "anthropic", "prices": { "<model key>": { "input": 3.0, "output": 15.0 } } },
  "calls": [ { "t": 1000, "op": "assistant", "content": [...], "usage": {...}, "model": "..." } ],
  "expected": [ { "specversion": "1.0", "type": "avp.assistant_message", ... } ]
}
```

- `recorder`: constructor inputs. `prices` uses the price-table shape of
  `avp/bindings/python/src/avp/data/prices.json` (`models` entries).
- `calls`: in order. `t` is the clock in milliseconds; `op` names a Recorder
  method and the remaining keys are its arguments, spelled as the Python
  keyword arguments: `prelude` (`commission`, `descriptor`), `start`
  (`request_model`, `prompt`, `system_prompt`, `tools`, `mcp_servers`, `skills`,
  `subagents`, `session_id`, `thread_id`, `tags`, `meta`), `assistant`
  (`content`, `usage`, `model`, `request_model`, `turn_key`, `finish_reasons`,
  `meta`, `cost_usd`, `duration_ms`), `close_turn`, `tool_result` (`call_id`,
  `content`, `is_error`, `structured_content`), `subagent_start`
  (`invocation_id`, `name`, `input`, `description`), `subagent_result`
  (`invocation_id`, `text`, `reason`, `usage`, `structured`), `error` (`code`,
  `message`), `stop` (`reason`, `output`). Wire objects (content blocks, usage,
  tool decls, Commission, descriptor) appear in their wire form.
- `expected`: the events written to the sink, serialized as NDJSON lines are
  (aliases, nulls omitted).

## Runner contract

- **Clock.** Time stands still between calls. Before each call set the clock to
  `t`: `monotonic` returns `t / 1000` seconds, and event `time` is
  `2026-01-01T00:00:00.000Z` plus `t` milliseconds, formatted
  `YYYY-MM-DDTHH:MM:SS.mmmZ`.
- **Ids.** The trace id is `0af7651916cd43dd8448eb211c80319c`. Span ids and
  event ids may come from any deterministic source; before comparing, rename
  every event `id` to `evt-N` and every `span_id` / `parent_span_id` to
  `span-N` by order of first appearance on the wire (the zero parent
  `0000000000000000` stays). The span tree is the contract, not which id a
  binding mints first.
- **Compare** the normalized events for equality, in order. Floats (cost) must
  match to 1e-12.

## Changing a rule

Change the Python Recorder, regenerate with
`AVP_UPDATE_RECORDER_VECTORS=1 uv run pytest avp/bindings/python/tests/test_recorder_vectors.py`,
review the diff, then bring the Rust and TypeScript Recorders back to green.
