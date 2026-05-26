# avp — Python reference implementation for the Agent Voyager Project v0.1

Spec: [`spec/v0.1/`](../../spec/v0.1/)
Conformance suite: [`conformance/v0.1/`](../../conformance/v0.1/)

This package ships:

- **Wire types** — Pydantic v2 models for every Commission, Event, and AgentDescriptor variant in v0.1, with discriminated unions on `type`. Defined in spec-scoped modules: `avp.commission`, `avp.descriptor`, `avp.trajectory`, `avp.resolver`. The top-level `avp` package re-exports them for `from avp import Commission` ergonomics.
- **NDJSON IO** (`avp.io`) — line-buffered stdio readers and writers for the Commission (in) + Event trajectory (out).
- **Reference agent** (`avp.agent`) — implements the normative loop in [`trajectory.md` §3.2](../../spec/v0.1/trajectory.md#32-the-loop). Pluggable model and tool drivers (mock drivers ship with the package for testing).
- **Conformance harness** (`avp.conformance`) — loads test-case files from the v0.1 conformance suite, drives the reference agent with scripted model / tools / resolver, asserts captured trajectory against the expectations. CLI: `avp-conformance` (subcommands `ping` / `check` / `validate`).

The reference agent is the gate for AVP v0.1 correctness. All conformance cases MUST pass before any other AVP-compliant agent (e.g. a closed-source Rust supervisor talking to a real-LLM agent) is wired up against it.

## Quickstart

The repo is a uv workspace; bootstrap once from the repo root:

```bash
cd /path/to/agent-voyager-project
uv sync
```

Then:

```bash
uv run pytest python/avp                  # runs every test in this package
uv run avp-conformance validate           # TestCase-validate every packaged case file
```

## Package layout

```
src/avp/
  __init__.py           # public re-exports
  enums.py              # Source, StopReason, ErrorCode helpers
  types.py              # Pydantic models for Commission / Event
  io.py                 # NDJSON readers / writers
  agent/
    __init__.py         # public re-exports
    agent.py            # AVPAgent — the loop
    drivers.py          # ModelDriver, ToolDriver, SubagentDriver protocols
    local_tools.py      # LocalTools — generic in-process tool driver
    mock.py             # ScriptedModel, ScriptedTools for tests
  conformance/
    __init__.py
    matcher.py          # partial-match patterns + {{event.*}} substitution
    harness.py          # runs one case end-to-end
    cli.py              # `avp-conformance` entry point
```

