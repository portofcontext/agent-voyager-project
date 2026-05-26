# Conformance refactor plan

Slim, single-runner conformance for AVP v0.1.

## Goals

- One canonical conformance runner: `avp-conformance` CLI in `python/avp`.
- Cases ship inside the `avp` Python package, gated behind an extras group.
- SDK authors only implement a conformance subprocess entrypoint, not a harness.
- Wire-level contract (manifest + stdin payload + NDJSON trajectory) is the only cross-language artifact.

## Decisions

- **Cases move into `python/avp`.** New home: `python/avp/src/avp/conformance/cases/v0.1/`. Top-level `conformance/v0.1/` directory is retired.
- **Cases are package data.** Shipped via `[tool.hatch.build.targets.wheel.force-include]` (or equivalent), not as a sibling repo dir.
- **Extras gate the install.** `pip install avp[conformance]` pulls cases + CLI deps. Bare `pip install avp` excludes both.
- **CLI is gated too.** `avp-conformance` entry point still registers, but errors with a clear "install `avp[conformance]`" message when the extra isn't present.
- **HARNESS.md is deleted.** Replaced by a short paragraph in the package's conformance README.
- **AGENT-CLI.md is the only normative SDK-facing doc.** Lives at `python/avp/src/avp/conformance/AGENT-CLI.md`.
- **Manifest format is JSON, not TOML.** Consistent with the rest of the wire.
- **Pydantic is the source of truth for case + manifest shape.** No hand-maintained JSON Schema files. If one is ever needed externally, generate it from the models, same pattern as `avp.commission` / `avp.descriptor` / `avp.trajectory`.
- **No embedded reference agent.** Per `python/avp/CLAUDE.md`. The CLI shells out to the SDK under test for every `run` invocation.
- **Agent CLI contract: `run` + `ping` subcommands.** Commission delivered via `--commission <json|path>`; trajectory written to `--out <path.jsonl>`; `ping --out <path>` writes `{"type": "pong"}` as a liveness check. The conformance CLI appends these subcommands + flags to the manifest's `command` prefix.
- **Cases are cross-SDK; built-ins are injected as fixtures.** A test case's optional `built_in` field tells the SDK what to pretend its built-ins are for the run (system prompt, tools, skills, mcp_servers, subagents). The SDK then applies Commission overrides per spec. This is how merge / override behavior gets tested deterministically across any SDK without coupling case files to a specific implementation.
- **No stubbing of model / tool / resolver outcomes.** Cases run against the SDK's real model; expectations are structural (event ordering, source field, presence of fields), not numeric. Numeric bounds on `final_state` remain available for SDKs that opt into determinism.
- **Written from scratch.** `avp/archive/conformance/` is a read-only reference; do not import from it or port code verbatim. Skim it for prior decisions, then write fresh against the slim plan below.

## Out of scope (for this refactor)

- Multi-version case selection (`--suite v0.2`). v0.1 only for now; version dir layout supports it but no CLI flag yet.
- Per-SDK harness libraries. The contract is the subprocess wire, nothing else.
- Case-file shape redesign. Existing `scripted_*` blocks stay; whether they evolve is a follow-up.
- Generated JSON Schemas for case + manifest. Pydantic models are enough until an external consumer needs them.

## CLI surface

```
avp-conformance ping  --agent <manifest.json>
avp-conformance check --agent <manifest.json> --suite v0.1
avp-conformance check --agent <manifest.json> --case <path>
avp-conformance validate --suite v0.1
```

- `--suite v0.1` resolves to the packaged cases dir; no walk-up needed.
- `--agent` is required for `ping` and `check`.
- `validate` works on packaged cases without an SDK.

## Manifest shape (JSON)

```json
{
  "command": ["uv", "run", "python", "-m", "avp_anthropic.conformance"],
  "cwd": ".",
  "env": { "AVP_CONFORMANCE_MODE": "1" },
  "description": "avp-anthropic SDK adapter"
}
```

- `command` is the prefix the conformance CLI invokes. It appends `run --commission ... --out ...` or `ping --out ...` per the agent CLI contract below.
- `cwd` resolved relative to the manifest's location, not the conformance CLI's CWD.
- Pydantic model `avp.conformance.manifest.AgentManifest` is the source of truth.
- Validated on load; same error path as case-file deserialization.

## Agent CLI contract (AGENT-CLI.md)

The SDK under test exposes a CLI binary with two subcommands. The
conformance CLI invokes them by appending to the manifest's `command`.

### `run --commission <json|path> [--built-in <json|path>] --out <path.jsonl>`

- `--commission` accepts either an inline JSON string OR a path to a JSON file containing the Commission.
- `--built-in` (optional) accepts inline JSON OR a path to a JSON file matching `avp.conformance.case.AgentBuiltins`. When present, the SDK MUST behave for this run as if those are its actual built-ins, then apply Commission overrides per the AVP merge spec. When absent, the SDK uses its real built-ins.
- `--out` is a path to a JSONL file the agent writes AVP trajectory events to (one event per line, emission order, until `agent_stopped`).
- Exit `0` after `agent_stopped`. Non-zero is a crash; the conformance CLI surfaces stderr tail.
- Stdout / stderr are free-form logging, ignored by the conformance CLI.

### `ping --out <path.jsonl>`

- Writes a single line `{"type": "pong"}` to the output file, then exits `0`.
- Used by the conformance CLI to verify the agent binary is invocable + can write to the given path before any case is run.

### Required, not optional

An SDK that doesn't expose both subcommands matching this shape cannot be driven by the conformance CLI.

## Progress checklist

### Package + cases
- [x] Add `[project.optional-dependencies] conformance = [...]` to `python/avp/pyproject.toml`.
- [x] Update workspace root (`python/pyproject.toml`) to pull `avp[conformance]` so `uv sync` installs typer for dev.
- [x] Move `conformance/v0.1/cases/` → `python/avp/src/avp/conformance/cases/v0.1/archive/` for review and per-case promotion to the new six-field shape.
- [ ] Review archived cases one by one in to `cases/v0.1-archive/` & promote/rewrite relevant cases rewritten against the new `TestCase` model.
- [ ] Configure package data so cases ship in the wheel under the `conformance` extra.
- [x] Delete top-level `conformance/v0.1/` once promotion is complete (HARNESS.md, schema dir, validate.py, README).

### Pydantic models
- [x] Add `avp.conformance.manifest.AgentManifest`.
- [x] Add `avp.conformance.case.TestCase` (six-field shape: `id`, `title`, `description`, `spec_refs`, `built_in`, `commission`, `expectations`).
- [x] Add `avp.conformance.case.AgentBuiltins` + `Builtin{Tool,Skill,McpServer,Subagent}` fixture types.
- [x] Drop stubbing fields (`scripted_model`, `scripted_tools`, `scripted_resolver`, `omit_resolver`, `agent_descriptor`, `agent_builtin_tools`, `applies_to`).

### CLI (write fresh under `python/avp/src/avp/conformance/`)
- [x] Scaffold CLI surface: `__init__.py`, `cli.py` (import-error gate), `_app.py` (Typer app).
- [x] Wire `run` / `validate` subcommands and the `--agent` / `--suite` / `--case` flags per the CLI surface above (stub bodies).
- [x] Implement `ping --agent <manifest>`: loads manifest, spawns agent, validates pong response.
- [x] Gate the CLI behind the `conformance` extra (clear error when not installed).
- [x] Implement `validate`: load every packaged case via `TestCase`, report per-file failures.
- [x] Implement `check` (load side): load manifest, discover cases by `--suite` or `--case`, group by category subdir, print summary.
- [ ] Implement `check` (dispatch side): spawn agent subprocess with `run --commission --built-in --out`, capture jsonl, match expectations.
- [ ] Implement matcher: `in_order_subsequence` / `in_order_strict` / `any_order`, `forbidden_events`, `final_state`.

### Docs
- [ ] Write `python/avp/src/avp/conformance/AGENT-CLI.md` (agent `run` + `ping` subcommand contract + manifest fields, with the pydantic model as cited source of truth).
- [ ] Write `python/avp/src/avp/conformance/README.md`: short walk-through of the CLI (`run`, `validate`), manifest example, where cases live, link to AGENT-CLI.md for the agent-side contract.
- [ ] Update top-level `README.md` and `CLAUDE.md` references to the new path.

### Reference SDKs
- [x] Add `avp-conformance.json` manifest + `conformance.py` entrypoint to `python/agents/avp-claude-agent-sdk/` (ping verified end-to-end; run is a stub).
- [x] Implement the `ping` subcommand in each entrypoint (Commission → trajectory NDJSON).
- [ ] Implement the `run` subcommand in each entrypoint (Commission → trajectory NDJSON).
- [ ] Confirm `avp-conformance check --agent <manifest> --suite v0.1` drives both end-to-end.

### CI / Make
- [ ] Update `make conformance` to install the extra and run the new CLI shape.
- [ ] Verify `make check` still passes end-to-end.

### Future: monorepo CI/CD configs
- [ ] Commit a manifest per in-repo SDK at a predictable location (e.g. `<sdk>/avp-conformance.json`).
- [x] Add `make conformance` (or equivalent) that runs every committed manifest against the packaged suite.
- [ ] Wire that target into CI so PRs touching any SDK or the spec re-run the full matrix.
- [ ] Decide whether to fan out per-SDK as separate CI jobs (parallelism + clearer failures) or one job (simpler).
