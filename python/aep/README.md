# aep — Python reference implementation for Agent Execution Protocol v0.1

Spec: [`spec/v0.1/`](../../spec/v0.1/)
Conformance suite: [`conformance/v0.1/`](../../conformance/v0.1/)

This package ships:

- **Wire types** (`aep.types`) — Pydantic v2 models for every Config / Event / SupervisorMessage variant in v0.1, with discriminated unions on `type`.
- **NDJSON IO** (`aep.io`) — line-buffered stdio readers and writers for trajectories and supervisor messages.
- **Reference runner** (`aep.runner`) — implements the normative loop in [`SPEC.md` §10.3](../../spec/v0.1/SPEC.md#103-the-loop): strict-greater boundary, hook lifecycle, supervisor-tool lifecycle, re-observation lifecycle. Pluggable model and tool drivers (mock drivers ship with the package for testing).
- **Conformance harness** (`aep.conformance`) — loads test-case files from the v0.1 conformance suite, drives the reference runner with scripted model / tools / supervisor, asserts captured trajectory against the expectations. CLI: `aep-conformance --suite path/to/cases`.

The reference runner is the gate for AEP v0.1 correctness. All 21 conformance cases MUST pass before any other AEP-compliant runner (e.g. a closed-source Rust supervisor talking to a real-LLM runner) is wired up against it.

## Quickstart

```bash
pip install -e .[dev]
pytest                                      # runs the conformance suite as tests
aep-conformance --suite ../../conformance/v0.1/cases   # standalone CLI
```

## Package layout

```
src/aep/
  __init__.py           # public re-exports
  enums.py              # Source, StopReason, ErrorCode, OnFailure, verifier-trigger helpers
  types.py              # Pydantic models for Config / Event / SupervisorMessage
  io.py                 # NDJSON readers / writers
  runner/
    __init__.py         # AEPRunner — the loop
    boundary.py         # strict-greater check_consumption + check_step_projection
    interactions.py     # supervisor interaction primitives (hook, tool_exec, re_observation)
    drivers.py          # ModelDriver, ToolDriver, SupervisorDriver protocols
    mock.py             # ScriptedModel, ScriptedTools, ScriptedSupervisor for tests
  conformance/
    __init__.py
    matcher.py          # partial-match patterns + {{event.*}} substitution
    harness.py          # runs one case end-to-end
    cli.py              # `aep-conformance` entry point
```

