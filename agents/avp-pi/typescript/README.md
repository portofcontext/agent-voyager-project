# avp-pi

AVP adapter for the [Pi coding agent](https://github.com/earendil-works/pi)
(`@earendil-works/pi-coding-agent`), built on the TypeScript binding's
`Recorder`. Pi owns the loop, tools, and MCP connections; the adapter maps the
Commission into a Pi session and reports Pi's session events.

Requires Node 22.19 or newer. Install the released agent with
`avp agent install pi`; sandboxed runs install Node and the same archive from
the agent's container recipe.

```bash
make pi-build                      # npm ci + build (binding and adapter)
make test-pi                       # seam tests on Pi's scripted faux model
node dist/src/main.js describe     # Pi's default tools: read, bash, edit, write
node dist/src/main.js run --commission commission.json --out trajectory.ndjson
make pi-check                      # v0.1 conformance on a real model (paid)
scripts/package.sh                 # the release archive, dist/release/avp-pi.tar.gz
```

Releases: bump `version` in `package.json` and `container_version` for `pi` in
`avp-cli/src/avp_cli/agents.py` together, then `make release-pi` from a clean
`main`.

## Mapping

| Commission | Pi |
|---|---|
| `model` `<origin>/<id>` | Pi catalog model `<origin>` / `<id>`; unknown is `unsupported_model` |
| `provider.base_url` | the model's endpoint; without it, a launcher's `<ORIGIN>_HOST` replaces the endpoint's root. A `provider.id` other than the origin is `unsupported_provider` |
| `system_prompt` | appended to Pi's system prompt, which keeps its tool and skill guidance |
| `prompt` | the session's single prompt |
| `skills` | written to a scratch directory and loaded as Pi skills |
| `mcp_servers` | Pi's MCP extension with `direct` exposure: tools are `mcp__<server>__<tool>` |
| `enabled_builtin_tools["avp-pi"]` | Pi's enabled tools, among `read`, `bash`, `edit`, `write` |
| `output_schema` | ignored; Pi has no structured final output |

Pi ships no subagents, so the subagent conformance case reports SKIP.

## Runtime

- Each assistant `message_end` is one turn, with Pi's usage converted to AVP's
  convention (input includes cache reads and writes). Cost comes from the AVP
  price table, not Pi's.
- Each `tool_execution_end` is the paired tool result.
- A final assistant error becomes `error_occurred` plus `agent_stopped(error)`;
  an abort (SIGINT/SIGTERM) stops as `interrupted`.
- Settings and sessions are in memory. Extensions, prompt templates, themes,
  and skills are not discovered, and install telemetry is off. Credentials come
  from Pi's usual sources: the provider's environment variable
  (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, ...) or `auth.json` in Pi's agent
  directory. Context files (`AGENTS.md`) load as they do in Pi.
- MCP servers are dialed once before `agent_started` to list their tools; a
  server that fails is reported as `mcp_connect_failed` and left out. Pi then
  connects the reachable ones itself, with transports built from the
  Commission's literal values (Pi's `${VAR}` / `!command` expansion is not
  applied).
