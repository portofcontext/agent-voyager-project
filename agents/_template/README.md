# Agent template

Starting point for a new AVP agent (an adapter over a harness that owns its
own loop). Python in `python/`, Rust in `rust/`. Each runs end to end out of
the box against a scripted stand-in harness, so its tests pass before you
change anything.

An adapter is four small parts. Only the first two are yours to write; the
binding does the rest.

| File | You write | The binding does |
|---|---|---|
| `commission` | Commission → harness config; `fail_fast` checks | |
| `translate` | native content / usage → AVP blocks / `Usage`; stop reasons | |
| `agent` | wire harness events to Recorder calls; `describe()` | `Recorder`: ordering, spans, steps, tool pairing, cost |
| `conformance` / `main` | nothing | `agent_cli`: `ping` / `describe` / `run` |

## Steps

1. Copy `python/` or `rust/` to `agents/<name>/<lang>/`; rename the package,
   `AGENT_NAME`, and the module in `avp-conformance.json`. Python: add the
   directory to the root `pyproject.toml` workspace members and `TEST_PKGS` in
   the `Makefile`.
2. Replace `harness` with the real SDK and map its events in `agent`. The rules
   that matter:
   - Report each inference with `assistant(...)`, tool calls as `tool_use`
     blocks in its content. Streamed chunks of one inference share a
     `turn_key`; a complete message per inference passes none.
   - Report each result with `tool_result(call_id, ...)`.
   - Usage that arrives after the content: keep the turn open with a
     `turn_key` and call `usage(...)` before the next inference.
   - Subagents: `subagent_start` / `subagent_result`, keyed by the tool call id
     that spawned them.
   - End every path with `stop(reason)`; on an exception, `error(...)` first.
3. Fill in `commission`: model, system prompt, prompt, the `enabled_builtin_*`
   allow-lists under `AGENT_NAME`, inline `mcp_servers` and `skills`.
4. Keep the seam test, pointed at a recorded or stubbed SDK stream.
5. Run the free checks (`avp-conformance ping` / `describe --agent
   <manifest>`), then the suite on a real model (`avp-conformance check
   --agent <manifest> --suite v0.1`).

The checklist with commands: `avp/core/conformance/src/avp_conformance/CHECKLIST.md`.
Worked adapters: `agents/avp-claude-agent-sdk/python/` (streamed chunks, async
subagents) and `agents/avp-goose/rust/` (late usage, subagents via a tool).
