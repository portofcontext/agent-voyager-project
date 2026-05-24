# avp-goose tech debt

Running ledger of known shortcuts and follow-ups. Add to it as work lands;
clear items when fixed. Not blockers — deliberate, recorded debt.

## Cleared
- Final-output tool filtered out of the descriptor (`tool_decls`).
- `cost_source` reports `unknown` for zero-usage turns (not `computed $0`).
- Error classification: stream errors map to `rate_limit`/`context_limit`/
  `auth_error`/`agent_crash` via `classify_error` (was always `agent_crash`).
- `enabled_builtin_tools` semantics decided: each listed name is enabled as a
  builtin extension; `None` enables none (the Commission lists what it wants).
  This intentionally differs from AVP's implied "None = all" because the run is
  an isolated, Commission-defined environment.
- `GOOSE_VERSION` (descriptor `agent_version`) now derived from Cargo.lock by
  `build.rs` instead of hardcoded.
- `CapturingSink` deduped: src unit tests share `src/testkit.rs` (integration
  tests keep their richer `tests/common` harness).
- **Per-turn usage + cache split** via the provider tap (`provider_tap.rs`): a
  `Provider` decorator tees per-inference `ProviderUsage` (incl. cache
  read/write) off the stream, so each turn carries its own real cost. Replaces
  the lagging session-token diff (which lumped all cost on the final turn).
  Live-verified: a tool round distributed `$0.000875` + `$0.022120` across its
  two inferences.
- **Streaming-delta coalescing** (`translate::append_coalescing` + the runner
  loop): Goose's live `reply()` stream yields an assistant inference as
  incremental message deltas (`"av"` then `"p-tool-ok"`), and the runner used to
  emit one `assistant_message` per delta, fragmenting a single turn into many.
  The runner now accumulates consecutive assistant messages into one turn,
  closing it at the next non-assistant message or stream end (a new inference
  only follows tool execution, so the boundary is unambiguous). Cross-provider
  live-verified: a one-line reply is now 1 turn, a tool round is 2.
- **Cross-provider eval harness** (`src/bin/avp-goose-eval.rs`): runs a matrix
  of Commission setups × providers by spawning `avp-goose-run` per case (fresh
  process per case, since Goose's `Config`/`SessionManager` are global), schema-
  validates each trajectory, and scores declarative evals. 6/6 pass on Sonnet
  (Anthropic) + GPT-4o (OpenRouter).
- **Live MCP dispatch confirmed, on a stable in-repo fixture.** Replaced the
  machine-specific `gtmagent` test reference with a tiny self-contained stdio
  MCP server (`testing/mcp/avp_test_mcp.py` at the repo root, shared across
  suites; arcade-mcp-server, deps inline for `uv run`). Two gated tests use it
  (`make test-mcp`): `mcp_connect` (no key)
  proves Goose connects and lists its tools; `live_mcp` drives a real model that
  dispatches to the server, asserting `dispatch_target=mcp_server`, a successful
  `tool_returned`, and the echoed token round-tripping. Both isolate via
  `GOOSE_PATH_ROOT`.

## Blocked on a Goose in-loop signal
- **Stop-reason fidelity.** Only `converged`/`error` emitted. `interrupted`
  needs a wired cancel token (max_turns/timeout); `refused` needs a model-refusal
  signal Goose does not surface on the stream (the provider tap may expose a
  finish reason — to investigate).

## Needs a live run with goose-side setup (emit/schema already proven)
- **Subagents** (needs configured subrecipes) — and **subagent token
  attribution**: `subagent_returned.avp.subagent.usage` is omitted; confirm
  whether the child `Agent` shares the parent session (if not, surface child
  usage).
- **Skills discovery** — files are written + the `skills` platform extension
  enabled; confirm Goose loads it and discovers them.
- **MCP `protocol_version`** is still a constant `"2025-06-18"`. There is now a
  real MCP server in the loop (`avp_test_mcp.py`, which negotiates `2025-06-18`),
  so the negotiated version can be surfaced from the connected extension instead
  of hardcoded; not yet wired.
- **`subagent_returned.reason`** is always `converged` (Goose doesn't surface the
  child's stop reason).

## Accepted (revisit at upstream; not worth churning now)
- **Per-turn input tokens follow Goose's additive accounting.** Goose sums every
  `ProviderUsage` it sees, and a provider can report usage more than once per
  inference (Anthropic reports at `message_start` and `message_delta`). The tap
  sums the same way, so a turn's totals match Goose's own metrics by
  construction. If a provider re-reports input across stream chunks this can
  over-count input vs. the provider's bill; consistency with Goose is the chosen
  invariant. Cross-provider cost is best-effort from the bundled price table
  (`openai/gpt-4o` priced at the OpenAI list rate); production should override.
- **`trajectory::Commission` vs `commission::AvpV01Commission` round-trip** — a
  2-line serde bridge for the schema's embedded types. Inherent to the
  embedded-commission shape; only removable by changing schema generation.
- **Goose git dep pinned to a `main` rev** (`728d72a`). Works and is isolated
  from the user's install; track a release tag for an external crate, moot once
  upstreamed into the Goose tree.
