# avp-goose tech debt

Running ledger of known shortcuts and follow-ups. Add to it as work lands;
clear items when fixed. Not blockers — deliberate, recorded debt.

## Blocked on a Goose in-loop signal
- **Stop-reason fidelity.** Only `converged`/`error` emitted. `interrupted`
  needs a wired cancel token (max_turns/timeout); `refused` needs a model-refusal
  signal Goose does not surface on the stream (the provider tap may expose a
  finish reason — to investigate).
- **`subagent_returned.reason` on the success path is always `converged`.** Goose
  doesn't surface the child's stop reason; the error path correctly reports
  `error` (mirrors the paired `tool_returned` is_error).

## Code TODOs (small follow-ups, no goose signal needed)
- **Subagent token attribution.** `subagent_returned.avp.subagent.usage` is
  omitted. The summon path is wired + live-validated (`live_subagent`), but the
  child's spend isn't surfaced; confirm whether the child `Agent` shares the
  parent session (if not, roll up the child's tokens onto the event).
- **Descriptor `mcp_servers[].status` is hardcoded `connected`.** The runner
  loads servers via `add_extensions_bulk` but does not read the per-server
  `ExtensionLoadResult`, so a failed dial is not reflected as `failed`. Wire the
  load results through `build_descriptor`.
- **Price-table mapping report.** Copy Goose's `name_builder` "mapping report"
  lock-file idea so a model dropping out of the models.dev catalog is visible in
  the `sync-prices` diff. (The mirror, lookup normalization, Goose-equality, and
  the daily CI sync are done.)

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
  invariant.
- **`trajectory::Commission` vs `commission::AvpV01Commission` round-trip** — a
  2-line serde bridge for the schema's embedded types. Inherent to the
  embedded-commission shape; only removable by changing schema generation.
- **Goose git dep pinned to a `main` rev** (`728d72a`). Works and is isolated
  from the user's install; track a release tag for an external crate, moot once
  upstreamed into the Goose tree.
- **One committed `prices.json`, embedded cross-tree.** To avoid a per-language
  duplicate (the table is ~0.5MB and grows), the single canonical copy lives in
  the Python package and the Rust crate embeds it via
  `include_str!("../../../python/avp/src/avp/data/prices.json")`. The path is
  repo-relative, so it works for path/git deps and the upstream-into-goose path;
  a standalone crates.io/PyPI publish of `avp` would need the file vendored into
  each package (a `build.rs` copy for Rust, a build hook for Python). Revisit if
  we ever publish the crates independently.
- **Runs use an isolated workspace, not the caller's CWD.** The runner points
  Goose's working dir at `<path_root>/workspace`, so run-scoped state
  (`.agents/skills`, `.agents/recipes`) never pollutes the caller's directory and
  the Commission fully defines the environment. If a future use case needs the
  agent to operate on the caller's project tree, make the working dir
  Commission/env-configurable.
