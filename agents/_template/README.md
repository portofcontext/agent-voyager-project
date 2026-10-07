# Agent template

Starting point for a new AVP agent: an adapter over a harness (an agent SDK)
that owns its own loop. Python in `python/`, Rust in `rust/`. Each runs end to
end out of the box against a scripted stand-in harness, so a fresh copy passes
its tests and `ping` / `describe` before you change a line.

An adapter is two small files of yours on top of the binding:

| File | You write | The binding does |
|---|---|---|
| `commission` | Commission → harness config | `preflight`: the spec's pre-turn Commission checks |
| `translate` | native content / usage → AVP blocks / `Usage`; stop reasons | |
| `agent` | wire harness events to Recorder calls; `describe()` | `Recorder`: ordering, spans, steps, tool pairing, cost |
| `conformance` / `main` | nothing | `agent_cli`: `ping` / `describe` / `run` |

## 1. Scaffold

```bash
make new-agent NAME=avp-<sdk>          # Python
make new-agent-rust NAME=avp-<sdk>     # Rust
```

This copies the template to `agents/<NAME>/<lang>/`, renames the package, the
agent name (`AGENT_NAME`, the key Commissions use in per-agent allow-lists),
and the manifest command, and registers the agent in the uv workspace,
`make test`, `make conformance`, and ruff's first-party list. Run the
`next:` commands it prints.

## 2. Replace the stand-in harness

Delete `harness`, add the SDK as a dependency, and map its events in `agent`:

- **Inferences.** Report each with `assistant(...)`, tool calls as `tool_use`
  blocks in its content (the Recorder derives `tool_invoked` from them).
  Streamed chunks of one inference share a `turn_key`; a complete message per
  inference passes none, and should pass `duration_ms` (the Recorder only times
  chunks it sees).
- **Models and cost.** `model` is the response model (`avp.response.model` on
  the wire, and the price-table key). Pass `request_model` too: a dated
  snapshot id the table lacks is then priced as the requested model.
- **Tool results.** `tool_result(call_id, ...)`, keyed by the call id in the
  `tool_use` block.
- **Late usage.** Usage that arrives after the content: keep the turn open with
  a `turn_key` and call `usage(...)` before the next inference.
- **Subagents.** `subagent_start` / `subagent_result`, keyed by the id of the
  tool call that spawned the child. If the child's own model calls aren't
  visible, roll its spend up onto `subagent_result(usage=...)`.
- **Ending.** `stop(reason)` on every path. Expected failures (preflight,
  auth, rate limit, refusal) end with `stop` and return normally; a crash
  records `error(...)` and `stop(error)`, then re-raises (non-zero exit).
- **Files.** Tools that touch files resolve against `AVP_WORKSPACE`. Without
  it use a fresh temp directory, never the process CWD: an unsandboxed run
  starts in your source tree.
- **Imports.** Keep the SDK import inside `run` / `describe` so `ping` stays
  cheap.

## 3. Mirror what the harness ships

The descriptor records what the agent ships with, and the spec leaves that to
the agent: built-in tools, skills, and subagents are invisible to AVP except
through the descriptor (`avp/core/spec/v0.1/README.md` §1). So the descriptor
mirrors the harness; the adapter never adds built-ins of its own:

- **A product** (Claude Code, Goose) ships default tools, skills, subagents:
  declare exactly those.
- **A framework** (the OpenAI Agents SDK) ships agents with none: declare none.
  Tools then come only from the Commission's `mcp_servers`, and cases that
  exercise tools or subagents report SKIP.

The template's `echo` tool belongs to its stand-in harness; replace it.

## 4. Honor the Commission

In `commission`, map every field the harness can honor: `model`, `provider`
(refuse with `unsupported_provider` when the harness can't reach it),
`system_prompt`, `prompt`, `output_schema`, inline `mcp_servers` and `skills`,
and the `enabled_builtin_*` allow-lists under `AGENT_NAME`. Pass the names the
agent offers per surface to `preflight` (the template does this for tools);
add harness-specific refusals next to it.

## 5. Test and certify

- Keep the seam test, pointed at a recorded or stubbed SDK stream.
- Free: `make test` and `make conformance` (your agent's `ping` / `describe`).
- On a real model: `avp-conformance check --agent <manifest> --suite v0.1`.
  The cases pin a Claude model; run them on your provider's with
  `--model <origin>/<model>` (e.g. `openai/gpt-4o-mini`). A case that needs a
  surface your descriptor doesn't declare (e.g. subagents) reports SKIP.
  `--case <path>` runs one case; `--dump-dir <dir>` keeps the trajectories.

## 6. Ship

**Out of tree** (a third-party agent): nothing in this repo changes. Point the
`avp` CLI at the manifest (an eval's agent can be a manifest path), and give
the manifest a `container` block (`install` steps, in-sandbox `command`) so it
can run in the CLI's sandbox.

**In tree** (published from this repo, installable with `avp agent install`):

1. Register it in `AGENT_SOURCES` (`avp-cli/src/avp_cli/agents.py`): `kind`
   (`"python"` wheels or a `"binary"`), `tag_prefix`, `dev_manifest`,
   `descriptor_name`, `container_version`, and `module` / `dist` /
   `wheel_dists` (Python) or `binary_name` (binary).
2. Add a release workflow: copy `.github/workflows/release-claude-code.yml`
   (Python) or `release-goose.yml` (binary) and change the tag prefix.
3. Add a `release-<name>` target to the `Makefile`, copying
   `release-claude-code` / `release-goose`.
4. Release: bump the package version and `container_version` together, commit,
   and run `make release-<name>` from a clean `main`.

Worked adapters: `agents/avp-claude-agent-sdk/python/` (streamed chunks, async
subagents) and `agents/avp-goose/rust/` (late usage, subagents via a tool). Recorder rules: `avp/core/conformance/src/avp_conformance/recorder/v0.1/README.md`.
