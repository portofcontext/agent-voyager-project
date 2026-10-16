# Changelog

## Unreleased

These changes retain the v0.1 wire schemas.

### Added

- Shared Python, Rust, and TypeScript Recorders for trajectory ordering, spans, and accounting.
- Stock agent entrypoints, shared preflight checks, and Python/Rust adapter templates.
- OpenAI Agents SDK and Codex adapters, installable as `openai-agents` and `codex`.
- Pi coding agent adapter (TypeScript), installable with `avp agent install pi` and
  released as `agent-pi-v<version>`. The TypeScript binding gains the stock
  entrypoint and preflight checks, and the CLI a `node` agent kind (`--package`).
- Conformance checks accounting on every trajectory (the cache split inside
  `input_tokens`, `unknown` costs of zero, `computed` costs matching the price
  table) and adds cases for invalid provider credentials, the Commission system
  prompt, inline skills, and SIGTERM. Cases can set `credentials: "invalid"` and
  an `interrupt`.
- `avp-conformance check` meters provider traffic (`--meter`, on by default):
  a local proxy per provider reads each response's usage, and a case fails
  when the trajectory omits billed tokens or the agent ignores the endpoint
  variables. A `describe` that calls a model fails too.

### Changed

- Onboarding starts with the official AVP skill, updated for current CLI and adapter workflows.

- Managed launches use fresh home, workspace, and SDK state directories. Direct
  library calls inherit their caller's context.
- Goose uses v1.53.0 and requires Rust 1.94.1 or newer. Its old `events`,
  `provider_tap`, and `runstate` modules are removed; the emitter API has changed.
- Rust bindings preserve extension fields in an `extra` map.
- Claude no longer emits `claude_agent_sdk.chunks_merged` metadata.
- The trajectory spec defines `avp.cost.source` and requires SIGINT / SIGTERM to
  end the run with `agent_stopped(interrupted)`. The Python and TypeScript stock
  entrypoints cancel the run on those signals and exit 130.

### Fixed

- Skill archives preserve spec paths and include the referenced schemas and examples.

- Invalid Recorder reports fail visibly without corrupting valid state.
- Model-response boundaries, tool pairing, per-response usage, and cost accounting.
- Claude enforces `enabled_builtin_subagents` (as `Agent(<name>)` deny rules),
  `enabled_builtin_mcp_servers`, and an empty `enabled_builtin_skills`, which
  it had ignored; inline skills no longer hide the built-in ones. Preflight
  checks every Claude allow-list, not only tools.
- Provider endpoints follow one convention: `<PROVIDER>_HOST` is the root that
  stands in for the provider's origin and `<PROVIDER>_BASE_URL` adds the API's
  version path (`OPENAI_BASE_URL` ends in `/v1`). The CLI set both to the same
  value, and its broker dropped the version path, so vault-credentialed OpenAI
  and OpenRouter runs requested the wrong URL. Google runs now get endpoint
  variables, including `GOOGLE_GEMINI_BASE_URL`.
- Pi and Codex ignored the launcher's endpoint variables, so their traffic
  bypassed the credential broker. Pi now moves its catalog endpoint under
  `<ORIGIN>_HOST`, and Codex reads `OPENAI_BASE_URL`.
- Claude and Goose no longer generate session titles, model calls outside the
  loop the trajectory never recorded. Claude names its CLI session after the
  run; Goose turns session naming off.
- Claude turns recorded the `message_start` placeholder as `output_tokens`
  (typically 1). Each turn now carries its response's final `message_delta`
  usage.
- Claude's capability probe no longer calls the model. It sent its probe prompt
  to the CLI's default model on every run, spend the trajectory never recorded.
- Goose provider failures, cached-token double counting, and session-naming usage.
- Claude's `input_tokens` now include cache reads and writes, and a failed API call
  (for example an invalid key) is reported as `error_occurred` rather than as a
  model turn.
- OpenAI Agents treats an exhausted balance as `rate_limit` and closes the run
  instead of crashing. Goose and Pi stop as `interrupted` on SIGINT / SIGTERM.
- Conformance now verifies a managed MCP tool round trip, reports capability skips,
  and updates native provider routing with model overrides.
- CI covers stacked PRs, every Python package, Rust/TypeScript bindings, and native
  Codex tests on Linux and macOS.
