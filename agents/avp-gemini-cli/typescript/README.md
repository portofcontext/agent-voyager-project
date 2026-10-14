# avp-gemini-cli

AVP adapter for [Gemini CLI](https://github.com/google-gemini/gemini-cli),
driven in-process through its published core package
(`@google/gemini-cli-core`) and built on the TypeScript binding's `Recorder`.
Gemini CLI owns the loop, tools, subagents, skills, and MCP connections; the
adapter maps the Commission into a Gemini CLI configuration and reports its
native events.

Requires Node 22.19 or newer. Install the released agent with
`avp agent install gemini-cli`; sandboxed runs install Node and the same
archive from the agent's container recipe. Runs need `GEMINI_API_KEY` (the
Gemini API; Vertex AI and Google sign-in are not used).

```bash
make gemini-cli-build              # npm ci + build (binding and adapter)
make test-gemini-cli               # seam tests on Gemini CLI's scripted content generator
node dist/src/main.js describe     # Gemini CLI's default tools, subagents, and skills
node dist/src/main.js run --commission commission.json --out trajectory.ndjson
make gemini-cli-check              # v0.1 conformance on google/gemini-3.1-flash-lite (paid)
scripts/package.sh                 # the release archive, dist/release/avp-gemini-cli.tar.gz
```

Releases: bump `version` in `package.json` and `container_version` for
`gemini-cli` in `avp-cli/src/avp_cli/agents.py` together, then
`make release-gemini-cli` from a clean `main`.

## Why in-process

Gemini CLI's headless mode (`gemini -p`) runs `LegacyAgentSession` from its
core package, and the adapter runs that same session. Its
`--output-format stream-json` output was the alternative, but it streams text
deltas and reports usage only as run totals in a final `result` event, so it
cannot give per-response usage. In-process, the Gemini client's stream ends
every model response with one `Finished` event carrying that response's
`usageMetadata`, tool calls carry the call ids the scheduler's results use,
and the content generator sees subagent model calls under the `invoke_agent`
call that made them.

## Mapping

| Commission | Gemini CLI |
|---|---|
| `model` `google/<id>` | the Gemini model `<id>`, served as named; another origin is `unsupported_model` |
| `provider.base_url` | the Gemini API endpoint; a `provider.id` other than `google` is `unsupported_provider` |
| `system_prompt` | the user-level `GEMINI.md` in the run's private Gemini CLI home, which Gemini CLI appends to its system prompt |
| `prompt` | the session's single message, sent literally (no `@file` expansion) |
| `skills` | written to the private home's user skills directory; the model loads them with `activate_skill` |
| `mcp_servers` | Gemini CLI's MCP client (stdio, and streamable HTTP with headers); tools are `mcp_<server>_<tool>` |
| `enabled_builtin_tools["avp-gemini-cli"]` | Gemini CLI's headless tools; the rest are excluded |
| `enabled_builtin_subagents["avp-gemini-cli"]` | `codebase_investigator`, `cli_help`, `generalist`; the rest are disabled |
| `enabled_builtin_skills["avp-gemini-cli"]` | `skill-creator`, `antigravity-support`; the rest are disabled |
| `enabled_builtin_mcp_servers` | must be empty: Gemini CLI ships no MCP servers |
| `output_schema` | ignored; Gemini CLI has no structured final output |

## Runtime

- Each model response is one turn: thought summaries as `thinking` blocks,
  text, and `tool_use` blocks keyed by Gemini CLI's call ids. Usage converts
  to AVP's convention: `input_tokens` is `promptTokenCount` (which already
  includes `cachedContentTokenCount`) plus tool-use prompt tokens;
  `output_tokens` is `candidatesTokenCount` plus `thoughtsTokenCount`, which
  is also `reasoning_output_tokens`. Cost comes from the AVP price table for
  the served model (`modelVersion`).
- Tool results are the response parts the model sees next, taken from the
  scheduler's completed calls.
- `invoke_agent` calls open a subagent frame that closes before the call's
  tool result. The subagent's own model calls are not turns of this
  trajectory; their usage and cost roll up onto `subagent_returned`.
- Provider failures end with `error_occurred` (`auth_error`, `rate_limit`
  including exhausted quota, `context_limit`, `unsupported_model`, or
  `unknown`) and `agent_stopped(error)`, without a turn for the failed
  response. An abort (SIGINT/SIGTERM) stops as `interrupted`.
- Each run gets a private Gemini CLI home (`GEMINI_CLI_HOME`), so no user
  settings, extensions, policies, skills, subagents, OAuth state, or stored
  keys are read. The workspace is trusted, as the sandbox is the boundary: its
  `GEMINI.md` context, `.gemini/skills`, and `.gemini/agents` load as they do
  in Gemini CLI. Approval mode is YOLO, telemetry and usage statistics are off,
  hooks are off, and `ask_user` is left out as in Gemini CLI's headless mode.
- Gemini CLI promotes some Flash and Flash Lite ids to its newest release; the
  adapter turns that off so the Commission's model is the one served.
- MCP servers connect while Gemini CLI initializes, before `agent_started`; a
  server that fails is reported as `mcp_connect_failed` and left out.
- The release archive leaves out Gemini CLI's optional native modules (a PTY
  and the system keychain, with prebuilds for only some platforms). Its one
  required native module, `tree-sitter-bash`, ships a prebuild per platform,
  so one archive serves macOS and Linux on both architectures. The shell tool
  then runs commands as child processes. Without a
  `rg` binary on `PATH`, `grep_search` uses Gemini CLI's JavaScript grep.

## Gaps

- `output_schema` is ignored.
- Gemini CLI's utility model calls (chat compression, the loop-detection
  check) are not reported as turns, and their spend is not counted.
- Subagent model calls are rolled up, not reported turn by turn.
- Thought text is Gemini CLI's parsed summary (`**subject**` and
  description); thought signatures are not carried.
- Gemini CLI writes its own error reports (`gemini-client-error-*.json`) to
  the system temporary directory when a request fails.
