# Changelog

## Unreleased

### Fixed

- A rate-limited `avp eval share` says to try again in a few minutes instead
  of printing the site's raw error object.
- Claude Code and Codex declared their built-in tools by name only, so
  descriptors and `agent_started` carried no descriptions or input schemas.
  Claude's capability probe now records the definitions the CLI sends the
  model (from a local stand-in that refuses the request, so nothing is spent),
  including its subagent and skill descriptions.
  Codex ships the definitions its pinned CLI sends each verified model,
  regenerated with `scripts/capture_tools.py`.

### Added

- `avp-conformance describe` fails when a declared tool has no description or
  an `inputSchema` that is not an object schema. Freeform tools may omit the
  schema. The agent template declares both for its `echo` tool.

## 0.2.1 (2026-10-19)

### Changed

- `avp eval share` replaces `avp eval view`. It uploads a finished eval to
  agentvoyagerproject.com after a confirmation (`--yes` to skip it) and prints
  a short `/r/<id>` link that unfurls in Slack and expires after 30 days.
  `avp eval unshare` takes a link down with the delete token the share saved.
  Links that carried the whole eval in the URL are retired: they were too long
  to paste into chat.
- `avp --version` prints the CLI version.

### Fixed

- `avp init --dir` creates the directory instead of crashing when it is missing.
- The `llm-judge` scorer takes the canonical `anthropic/<model>` slug (a bare id
  still works) and rejects other providers with a clear message; it passed the
  slug straight to the Anthropic API, which refused it.
- A sandbox server started from another `AVP_HOME` answered health checks but
  refused this home's key, so every sandbox failed with "invalid credentials".
  The CLI now reports the conflicting server instead of reusing it.

## 0.2.0 (2026-10-19)

These changes retain the v0.1 wire schemas.

### Added

- Shared Python, Rust, and TypeScript Recorders for trajectory ordering, spans, and accounting.
- Stock agent entrypoints, shared preflight checks, and Python/Rust adapter templates.
- OpenAI Agents SDK and Codex adapters, installable as `openai-agents` and `codex`.
- Pi coding agent adapter (TypeScript), installable with `avp agent install pi` and
  released as `agent-pi-v<version>`. The TypeScript binding gains the stock
  entrypoint and preflight checks, and the CLI a `node` agent kind (`--package`).
- Gemini CLI adapter (TypeScript), installable with `avp agent install gemini-cli`
  and released as `agent-gemini-cli-v<version>`. The CLI's vault broker routes
  `google` credentials with `x-goog-api-key` and sets `GEMINI_API_KEY`.
- LangChain Deep Agents adapter, installable with `avp agent install deep-agents` and
  released as `agent-deep-agents-v<version>`, with `AvpCallbackHandler`, a LangChain
  callback handler that records any LangChain or LangGraph run through the Recorder.
- OpenCode adapter (TypeScript, a hermetic `opencode serve` per run), installable
  with `avp agent install opencode` and released as `agent-opencode-v<version>`
  with one archive per platform.
- Conformance checks accounting on every trajectory (the cache split inside
  `input_tokens`, `unknown` costs of zero, `computed` costs matching the price
  table) and adds cases for invalid provider credentials, the Commission system
  prompt, inline skills, and SIGTERM. Cases can set `credentials: "invalid"` and
  an `interrupt`.
- `avp-conformance check` meters provider traffic (`--meter`, on by default):
  a local proxy per provider reads each response's usage, and a case fails
  when the trajectory omits billed tokens or the agent ignores the endpoint
  variables. A `describe` that calls a model fails too. With no subagent
  rollups, each billed response must also be one turn's usage, so usage on
  the wrong turn fails even when the totals match.
- Tool-call conformance: cases for dependent rounds, parallel calls, and a
  tool that fails with an `isError` result or a protocol error
  (`Avptest_Fail` in the MCP fixture). A case's `tool_calls` judges each
  call's own result, and every trajectory is checked for tool pairing: each
  call invoked once under the turn that made it, returned once with its own
  id, and none left open in a converged run. PATTERNS.md gains the rules for
  translating native events.

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
- Subagent rollups carry the child's final usage. Claude's came from the task
  notification, taken before the child's last response completed, and its
  result text was the task description; both now come from the `Agent` tool
  result. Goose's had no usage; it now reads the child session's totals. A
  Goose subagent launched in the background (`delegate` with `async`) closed
  at launch with no result; its frame now closes when `load` returns the
  result, or as `abandoned` at stop, after which the run no longer reports
  `converged`.
- Claude and Goose split a response with several tool calls into one turn
  per call, because both runtimes run a tool as soon as its call streams in;
  the extra turns repeated the response's usage. Results are now held until
  the response completes, so it is one turn with all its calls.
- OpenAI Agents recorded an MCP result flagged `isError` as a success, with
  its content as a JSON string of SDK items. It is now `is_error: true` with
  text blocks.
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
