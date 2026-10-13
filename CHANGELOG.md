# Changelog

## Unreleased

These changes retain the v0.1 wire schemas.

### Added

- Shared Python, Rust, and TypeScript Recorders for trajectory ordering, spans, and accounting.
- Stock agent entrypoints, shared preflight checks, and Python/Rust adapter templates.
- OpenAI Agents SDK and Codex adapters.

### Changed

- Onboarding starts with the official AVP skill, updated for current CLI and adapter workflows.

- Managed launches use fresh home, workspace, and SDK state directories. Direct
  library calls inherit their caller's context.
- Goose uses v1.53.0 and requires Rust 1.94.1 or newer. Its old `events`,
  `provider_tap`, and `runstate` modules are removed; the emitter API has changed.
- Rust bindings preserve extension fields in an `extra` map.
- Claude no longer emits `claude_agent_sdk.chunks_merged` metadata.

### Fixed

- Skill archives preserve spec paths and include the referenced schemas and examples.

- Invalid Recorder reports fail visibly without corrupting valid state.
- Model-response boundaries, tool pairing, per-response usage, and cost accounting.
- Goose provider failures, cached-token double counting, and session-naming usage.
- Conformance now verifies a managed MCP tool round trip, reports capability skips,
  and updates native provider routing with model overrides.
- CI covers stacked PRs, every Python package, Rust/TypeScript bindings, and native
  Codex tests on Linux and macOS.
