# avp — Python reference implementation for Agent Voyage Protocol v0.1

Spec: [`spec/v0.1/`](../../spec/v0.1/)
Conformance suite: [`conformance/v0.1/`](../../conformance/v0.1/)

This package ships:

- **Wire types** (`avp.types`) — Pydantic v2 models for every Commission / Event / SupervisorMessage variant in v0.1, with discriminated unions on `type`.
- **NDJSON IO** (`avp.io`) — line-buffered stdio readers and writers for trajectories and supervisor messages.
- **Reference agent** (`avp.agent`) — implements the normative loop in [`SPEC.md` §9.3](../../spec/v0.1/SPEC.md#93-the-loop): strict-greater boundary, supervisor-tool RPC lifecycle, verifier lifecycle. Pluggable model and tool drivers (mock drivers ship with the package for testing).
- **Conformance harness** (`avp.conformance`) — loads test-case files from the v0.1 conformance suite, drives the reference agent with scripted model / tools / supervisor, asserts captured trajectory against the expectations. CLI: `avp-conformance run` (subcommands `run` / `validate` / `check-coverage`).

The reference agent is the gate for AVP v0.1 correctness. All conformance cases MUST pass before any other AVP-compliant agent (e.g. a closed-source Rust supervisor talking to a real-LLM agent) is wired up against it.

## Quickstart

The repo is a uv workspace; bootstrap once from the repo root:

```bash
cd /path/to/agent-execution-protocol
uv sync
```

Then:

```bash
uv run pytest python/avp                  # runs every test in this package
uv run avp-conformance run                # runs the conformance suite (26 cases today)
uv run avp-conformance validate           # schema-checks the case files
uv run avp-conformance check-coverage     # every event type has at least 1 case
```

## Package layout

```
src/avp/
  __init__.py           # public re-exports
  enums.py              # Source, StopReason, ErrorCode, OnFailure, verifier-trigger helpers
  types.py              # Pydantic models for Commission / Event / SupervisorMessage
  io.py                 # NDJSON readers / writers
  agent/
    __init__.py         # AVPAgent — the loop
    boundary.py         # strict-greater check_consumption + check_step_projection
    interactions.py     # supervisor interaction primitives (tool_exec)
    drivers.py          # ModelDriver, ToolDriver, SupervisorDriver protocols
    mock.py             # ScriptedModel, ScriptedTools, ScriptedSupervisor for tests
  conformance/
    __init__.py
    matcher.py          # partial-match patterns + {{event.*}} substitution
    harness.py          # runs one case end-to-end
    cli.py              # `avp-conformance` entry point
```

