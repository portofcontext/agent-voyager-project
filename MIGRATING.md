# Migrating to the Recorder adapters

The Recorder stack changes library APIs, launcher behavior, and trajectory
accounting. The Commission, Agent Descriptor, and Trajectory JSON schemas stay
at v0.1 without shape changes.

## Library callers

- Rust generated structs now preserve unknown JSON fields in an `extra` map.
  Add `extra: Default::default()` to affected struct literals, or populate it
  when forwarding extension fields. Deserialization retains those fields.
- Goose removes the public `events`, `provider_tap`, and `runstate` modules.
  Integrations using these internals or `emit::Emitter` must migrate to
  `avp::recorder::Recorder` or the updated emitter API. The normal Commission
  runner remains the entrypoint for executing Goose.
- Recorder rejects invalid reports, including lifecycle misuse and unmatched
  tool results. Fix the translator when these errors surface; catching and
  discarding them produces an incomplete trajectory.
- Building Goose now requires Rust 1.94.1 or newer for Goose v1.53.0.

## Launch context

The CLI and conformance harness now supply fresh home, native SDK state, and
workspace directories through the shared `avp.launch` helpers. Supply credentials
and settings explicitly through the launcher environment; saved login sessions
and configuration in your usual home directory are no longer picked up by these
managed launches.

Stock Python and Rust agent CLIs enter `AVP_WORKSPACE` before describing or
running an agent. Direct library calls inherit their caller's context: the caller
owns directory creation, current directory, credentials, and cleanup. See
[launch context](PATTERNS.md#launch-context) for the shared convention.

## Trajectory consumers

Assistant messages now follow model-response boundaries, with per-response usage
and cost. Empty deliveries do not create model turns. Goose no longer counts
cached tokens twice or includes session-naming calls, and its assistant content
includes tool-use blocks. Claude no longer publishes `chunks_merged` metadata.
Zero-token responses have unknown cost rather than a fabricated zero.

Expect historical turn counts, durations, and costs to differ. Reduce usage and
cost from assistant-message deltas; do not add native cumulative session totals.
Treat `cost_source: "unknown"` as unavailable pricing, even when `cost_usd`
is zero.

## Conformance and releases

Conformance reports pass, fail, and skip separately. A skipped capability case
has not been verified. Compare adapters using both the results and their declared
capabilities; a passing supported subset is not full capability coverage.
`--model` also updates a fixture's native provider when changing origins, while
preserving explicit gateway routes and opaque credential handles.

OpenAI Agents and Codex are additional adapters. Their directories document the
supported capabilities and limitations, including Codex's experimental raw-event
observation. Conversation orchestration across Commissions remains out of scope.

Before publishing, bump the affected package versions and the CLI's matching
agent artifact pins together. Merging this stack does not publish a release.
