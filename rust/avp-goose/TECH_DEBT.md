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

## Planned: native provider routing in the Commission
- **`GOOSE_PROVIDER` is temporary.** Today the connector resolves the provider
  from the `GOOSE_PROVIDER` env var, so a Commission carrying `model:
  "openai/gpt-4o"` is ambiguous on its own (the model string only makes sense
  once you know the hidden provider). Asymmetric: `model` is on the wire but
  *where to run it* is not.
- **Agreed direction (designed, not yet built):** add an optional `provider`
  block to the Commission so routing is expressed natively:

  ```json
  "model": "openai/gpt-4o",
  "provider": {
    "id": "openrouter",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key_env": "OPENROUTER_API_KEY"
  }
  ```

  Split of concerns: **routing** (provider id + endpoint + model) belongs on the
  wire; **credentials** never do. `api_key_env` is a *reference* (a secret name),
  never the secret, so the Commission stays a safe, loggable artifact (see
  [[goose-connector-prod-auth-followup]]). All fields optional; absent ⇒ today's
  env behavior, so it is additive.
- **`base_url` reach:** covers the whole OpenAI-compatible ecosystem (OpenRouter,
  LiteLLM, vLLM, Together, Azure OpenAI, Groq, Ollama, LM Studio), which Goose
  already exposes per-provider as `<PROVIDER>_HOST`. It does NOT disambiguate
  non-OpenAI wire protocols (Anthropic-native, Bedrock SigV4, Vertex), so pair it
  with `id`: `base_url` + no `id` ⇒ assume OpenAI-compatible.
- **Goose mapping (feasible):** `provider.id` → the name passed to
  `goose::providers::create` (replacing the env read); `provider.base_url` → set
  `<ID>_HOST` before `create` (base_url is not on `ModelConfig`); `api_key_env`
  → Goose `get_secret` reads env first. The runner already sets env
  (`GOOSE_PATH_ROOT`), so this is the same mechanism, and the env var stops being
  a *user* requirement.
- **When built, sweep:** `commission.py` model → `make schemas` → `make bindings`
  (rust + ts) → connector mapping (`commission.rs` / `runner.rs`, drop the stale
  "intentionally not derived" comment) → both `examples/` (carry it in the
  Commission, not env) → `commission.md` prose → a conformance case pinning that
  the secret never appears inline.

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
