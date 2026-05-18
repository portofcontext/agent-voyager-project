# avp — refactor in progress

This package is being rewritten to be small and focused. The previous
implementation was AI-generated and grew into sprawl; it's archived under
`src/avp/archive/`. Do NOT import from there. It exists for review only.

## Goal: spec + thin SDK. Nothing more.

In scope:

- **Spec types** — `commission.py`, `descriptor.py`, `trajectory.py`.
  Pydantic models matching the JSON Schemas under `spec/v0.1/`. Source of truth.
- **`AVPAgent` base** — minimal with two modes: `sink` and `managaged`.
  - `def emit(event)` emits a trajectory event via some internal channel determined by the mode. e.g. `sink` will write to a db or to a file or to stdout, and `managed` will send over a websocket or something
    - `managed` mode will be alpha and `sink` will be beta
  - `run(commission)` No loop, no driver protocols, no auto-emitted events.
  Integrators subclass and implement `run`.
  - we might include more funcitonality in the base class but that will be in the future.
- **Serve stubs (ALPHA)** — `agent.serve_stdio()`, `agent.serve_ws()` to
  bind an `AVPAgent` to a transport effecting how the agent will emit trajectories and accept run committions. just stub for now, dont implement yet.
- **Resolver client + worked sample** — one client class for talking to a
  resolver service according to the resolver.md spec. The server itself is not in this repo for now.
- **Conformance harness** — validates an externally-produced trajectory
  against a case file. No embedded reference agent.

Out of scope here (belongs in the agent package that needs it, not in `avp`):

- Agent loops, driver protocols (`ModelDriver`, `ToolDriver`, etc.)
- MCP / skill / subagent dispatch helpers
- Opinionated tracers with scope ergonomics
- Multi-class resolver server/client abstractions

Duplication across two integrator packages is cheaper than a shared helper
that keeps regrowing.

## Working rules

- **Don't import from `archive/`.** Read it if useful, copy a small piece if
  it earns its place, but don't depend on it.
- **Add code only when the spec requires it or a second concrete caller
  already exists.** No helpers for hypothetical callers. If a pattern appears
  in one place, leave it inline.
- **Wire shape is pinned by conformance cases, not by code.** If you're
  tempted to add a class or helper to enforce a wire-shape rule, write a
  conformance case instead.
- **If a change adds more than ~50 lines outside the spec-derived Pydantic
  models, stop and check whether it really belongs in `avp` vs. in the
  integrator package.**
- **No regrowth of removed concepts.** If an idea was archived (driver
  protocols, opinionated tracer, dispatch helpers), don't reintroduce it
  under a different name. If the concept genuinely returns, raise it
  explicitly first.
