# avp — refactor in progress

This package is being rewritten to be small and focused. The previous
implementation was AI-generated and grew into sprawl; it's archived under
`src/avp/archive/`. Do NOT import from there. It exists for review only.

## Goal: spec + thin SDK. Nothing more.

In scope:

- **Spec types** — `commission.py`, `descriptor.py`, `trajectory.py`.
  Pydantic models matching the JSON Schemas under `avp/core/spec/v0.1/`. Source of truth.
- **Sink type + stdio sink** — `sink.py`. `EventSink` is the async-callable
  type for "consume one trajectory event"; `stdio_sink` is the trivial
  NDJSON-to-stdout built-in. No base class, no agent abstraction: integrator
  packages own their own agent shape and just take an `EventSink`.
- **Resolver client + worked sample** — one client class for talking to a
  resolver service according to the resolver.md spec. The server itself is not in this repo for now.

The **conformance harness** is NOT here anymore: it ships as the separate
`avp-conformance` package at `avp/core/conformance/` (it depends on these
types). Don't re-add a harness or case files to this package.

Out of scope here (belongs in the agent package that needs it, not in `avp`):

- Agent base classes / ABCs and any agent-lifecycle abstraction
- Agent loops, driver protocols (`ModelDriver`, `ToolDriver`, etc.)
- Transport stubs (serve_stdio, serve_ws) — deployment concern
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
