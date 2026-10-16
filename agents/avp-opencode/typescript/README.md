# avp-opencode

AVP adapter for [OpenCode](https://github.com/sst/opencode) (`opencode-ai`
1.18.34), built on the TypeScript binding's `Recorder`. OpenCode owns the loop,
tools, MCP connections, and subagents; the adapter starts a hermetic
`opencode serve` per run, drives one session through `@opencode-ai/sdk`, and
reports the server's event stream.

Requires Node 22.19 or newer. Install the released agent with
`avp agent install opencode`; sandboxed runs install Node, ripgrep, and the
Linux archive for the image's architecture from the agent's container recipe.

```bash
make opencode-build                # npm ci + build (binding and adapter)
make test-opencode                 # seam tests: the real server on a scripted model
node dist/src/main.js describe     # OpenCode's default tools, subagents, skills
node dist/src/main.js run --commission commission.json --out trajectory.ndjson
make opencode-check                # v0.1 conformance on a real model (paid; OPENCODE_MODEL=...)
scripts/package.sh                 # release archives, dist/release/avp-opencode-<platform>.tar.gz
```

Releases: bump `version` in `package.json` and `container_version` for
`opencode` in `avp-cli/src/avp_cli/agents.py` together, then
`make release-opencode` from a clean `main`.

## Mapping

| Commission | OpenCode |
|---|---|
| `model` `<origin>/<id>` | provider `<origin>`, model `<id>` from the catalog the binary bundles; an unknown model is `unsupported_model`, an unknown origin or one whose SDK OpenCode would install from npm is `unsupported_provider` |
| `provider.base_url` | the provider's `baseURL` |
| `provider.id` | the OpenCode provider that serves the model, when its catalog lists `<origin>/<id>` (OpenRouter, say) |
| `system_prompt` | the prompt's `system`, appended to OpenCode's system prompt |
| `prompt` | the session's single user message |
| `output_schema` | OpenCode's `json_schema` output format; the structured result is `agent_stopped`'s output |
| `skills` | written to a scratch directory listed in `skills.paths` |
| `mcp_servers` | OpenCode `local` (stdio) and `remote` (HTTP, OAuth off) servers; tools are `mcp__<server>__<tool>` |
| `mcp_servers[].auth` | `Authorization: Bearer` from `AVP_VAULT_<HANDLE>` |
| `enabled_builtin_tools["avp-opencode"]` | tools switched off on the prompt; withholding `edit` re-allows the `edit` permission that `write` and `apply_patch` share |
| `enabled_builtin_subagents["avp-opencode"]` | `deny` rules on the `task` permission |
| `enabled_builtin_skills["avp-opencode"]` | `deny` rules on the `skill` permission |

The descriptor is read from the server: OpenCode's registry tools (`bash`,
`read`, `glob`, `grep`, `edit`, `write`, `task`, `webfetch`, `todowrite`,
`skill`, `apply_patch`), its native subagents (`general`, `explore`), and its
built-in skill (`customize-opencode`). `agent_started` lists the tools the run's
model gets: OpenCode offers GPT models `apply_patch` in place of `edit` and
`write`. Left out: `invalid` (a repair target the model never sees),
`websearch` (off unless OpenCode's own provider or an Exa flag enables it), and
`question` (a headless client has no user to ask).

## Event sources

- **One turn per model request.** OpenCode makes one request per assistant
  message, bracketed by `step-start` / `step-finish` parts. Each root-session
  `step-finish` is one turn: the message's text, reasoning, and tool parts are
  the content, the part's tokens the usage. `message.updated` carries the same
  tokens, but only cumulatively per message and without a boundary event; the
  `session.next.*` events are not emitted by default.
- **Usage.** OpenCode subtracts cache reads and writes from `input` and
  reasoning from `output`; both are added back, so AVP `input_tokens` includes
  the cache split and `output_tokens` includes reasoning. Cost is computed from
  the AVP price table, not OpenCode's `cost` (which uses its own catalog), so
  it can be recomputed from the trajectory.
- **Tools.** Tool parts pair by `callID`. OpenCode runs a step's tools before
  the step finishes, so results follow their turn at once. Reporting after the
  fact, the Recorder's clock is pinned to OpenCode's timestamps (a response's
  last text end or tool start, a tool's end), so event times and durations are
  the real ones.
- **Subagents.** The `task` tool runs a child session. Its frame
  (`subagent_invoked` / `subagent_returned`) sits around the task call; the
  child's requests, and any grandchildren's, roll up onto
  `avp.subagent.usage` (tokens, turns, and computed cost), and its last text is
  the result. The Recorder places every turn under the agent span, so child
  turns are not emitted individually.
- **Ending.** The run ends when the root session is idle. A provider failure
  on the last request (`ProviderAuthError`, `APIError` by status or message,
  `ContextOverflowError`) becomes `error_occurred` + `agent_stopped(error)`
  with no turn. OpenCode retries rate limits itself; a retry whose reason is
  an exhausted quota or credit (OpenAI `insufficient_quota`) is aborted at once
  as `rate_limit`. An abort (SIGINT/SIGTERM) aborts the session, reports what
  the cut-off request streamed (no usage), and stops as `interrupted`.

## Runtime

- The server binds `127.0.0.1` on an ephemeral port with a random password,
  runs in its own process group, and is disposed and killed with the run,
  including on SIGTERM. Its config, data, and state directories are a per-run
  scratch directory; the Commission's config is inline. External plugins,
  sharing, autoupdate, model-catalog fetches, Claude Code prompt and skill
  discovery, default auth plugins, and LSP downloads are off. Workspace
  `opencode.json`, `.opencode/`, and `AGENTS.md` load as they do in OpenCode.
- Credentials come from the provider's environment variables
  (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...). A provider with none ends the
  run with `auth_error`.
- Permissions auto-allow (the run is sandboxed): `external_directory`, `.env`
  reads, and doom-loop prompts are allowed, and any remaining permission
  request is granted once.
- The cache directory is `$XDG_CACHE_HOME/avp-opencode` (default
  `~/.cache/avp-opencode`), where OpenCode downloads ripgrep when `rg` is not
  on PATH. Tools and stdio MCP servers inherit the server's XDG directories.
- MCP servers are connected by OpenCode; the adapter reads their status from it
  (a failure is `mcp_connect_failed`, and the run continues) and lists each
  connected server's tools once with the MCP SDK for the declarations.

## Distribution

OpenCode is a native binary per platform (`opencode-<os>-<arch>` npm
packages), so the release carries one archive per platform:
`avp-opencode-{darwin,linux}-{arm64,x64}.tar.gz`, each with exactly one binary,
fetched from npm at package time whatever the build host. `avp agent install
opencode` picks the host's archive; the container recipe picks
`linux-$(arch)`. Linux archives carry the glibc builds; `linux-x64` also
carries OpenCode's baseline build, used on CPUs without AVX2. Musl images are
not covered.

## Gaps

- Withheld subagents and skills are denied for every agent in the run,
  including subagents.
- Child-session turns are rolled up onto `subagent_returned`, not emitted.
- OpenCode's `{env:...}` / `{file:...}` substitution applies to Commission MCP
  values written into its config.
- `thread_id` is recorded but not resumed: every run is a fresh session.
