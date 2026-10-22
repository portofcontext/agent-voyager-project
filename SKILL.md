---
name: avp
description: >
  Set up and use AVP (Agent Voyager Project) to run agents, configure Commissions,
  compare agents or prompts with evaluations, and inspect trajectories. Use when
  onboarding to AVP, debugging an AVP run, or adapting an existing agent runtime
  to the Commission, Agent Descriptor, and Trajectory specs.
---

# Agent Voyager Project

AVP lets a supervisor send a **Commission** (task, model, resources) to an agent
and observe its **Trajectory** (model responses, tools, usage, cost, outcome).
The existing agent runtime owns execution. The supervisor configures once and
observes; v0.1 has no mid-run supervisor push channel.

Start with the user's task below. Read the linked reference only when needed.
Resolve relative reference paths from this skill's directory; run CLI commands
and create evaluation files in the user's project. Installing this skill adds
instructions, not the CLI or an agent runtime.

## Get a first evaluation running

1. Check for `uv` and the `avp` command. The CLI supports macOS and Linux.
   The default runtime needs a running Docker daemon. When the user selects
   local execution, or the task explicitly supplies an outer sandbox, use
   `--runtime local` on `avp run` and `avp eval run`. Local execution adds no OS
   isolation; do not silently select it when Docker fails.
2. Install missing components, then scaffold the small capitals example:

   ```bash
   uv tool install avp-cli
   avp agent install --all
   avp init capitals --agent claude-code
   ```

3. This example uses Anthropic. Use `ANTHROPIC_API_KEY` from the environment, or
   have the user configure it locally; never put credentials in project files
   or ask for them in chat. For another provider, inspect `avp eval run --help`
   and select a supported canonical `origin/model` with `--model`.
4. Inspect `capitals.eval.json` and its Commission files, then validate each with
   `avp cm check <id>`. Scaffolding and validation make no model calls.
5. Run `avp eval run capitals.eval.json`. Explain that execution makes paid model
   calls and the first run builds the container image. Report accuracy, pass
   rate, cost, and turns separately, and point to the saved run artifacts.

Use `avp --help` and subcommand help for the installed release's options.
`avp agent list` shows availability; prebuilt install names are `goose`,
`claude-code`, `codex`, `openai-agents`, `pi`, `gemini-cli`, `deep-agents`,
`pydantic-ai`, and `opencode` (Pi, Gemini CLI, and OpenCode need Node 22.19 or newer on the host for
`describe`; runs install Node in the sandbox).

## Configure a Commission or evaluation

Inspect `avp agent describe <name> --json` before choosing tools or capabilities.
Create a starting Commission with `avp cm create my-task --agent <name>`, edit
its JSON, then run `avp cm check my-task`.

- Commissions live at `~/.avp/commissions/<id>.json`; `AVP_HOME` overrides the
  library root. Required fields are `schema_version: "0.1"`, `run_id`, and
  `model` as `origin/model`. Start from the scaffold instead of guessing fields.
- `prompt`, `system_prompt`, and `output_schema` configure the task and output.
  `mcp_servers` carries inline stdio commands or HTTP connection details;
  `skills` carries inline files including `SKILL.md`.
- Built-in allowlists are **maps keyed by the descriptor's `agent_name`**:
  `"enabled_builtin_tools": {"goose": []}` disables Goose's built-in tools.
  Omit the field to expose all; a subset exposes only those exact names.
  A present map missing the running agent's key fails preflight. The same rules
  apply to `enabled_builtin_mcp_servers`, `_subagents`, and `_skills`.
  These filters do not disable Commission-managed MCP servers or skills.
- `agent_versions` pins exact descriptor versions. A mismatch fails before a
  model call; inspect the new descriptor before updating the pin.
- Eval JSON contains `name`, `agents`, `dataset`, `scorer`, and `commissions`
  (library IDs). Each Commission carries its own model. Clone a Commission and
  vary one field to make an interpretable comparison.
- Dataset sources are `inline`, `file`, and `huggingface`. Scorers are
  `exact-match`, `structural-match`, `structural-fidelity`, and `llm-judge`.
  Check the CLI guide for optional dependencies before using external datasets
  or scorers.

Read the [Commission spec](avp/core/spec/v0.1/commission.md) for field semantics
and the [CLI guide](https://github.com/portofcontext/agent-voyager-project/blob/main/avp-cli/README.md)
for eval configuration, provider routing, and credentials.

## Run a task in a project

Choose an image with the project's dependencies, then create an environment:

```bash
avp env create myproj --image python:3.12-slim --path ./my-project
avp run --agent goose --env myproj "Add type hints to utils.py, then run the tests"
```

The run uses a copy of the project and prints its resulting workspace and
trajectory paths. Inspect those outputs before claiming the task succeeded.
The launcher owns workspace staging, credentials, native runtime state, and OS
sandboxing. A Commission's tool allowlists do not replace OS confinement.
`--runtime local` uses the installed agent command and fresh native state without
creating another sandbox. Local environments accept `paths`, `files`, and `setup`;
container image, package, network, and resource settings are rejected.

## Diagnose a run

1. For startup failures, check `avp sandbox status`, agent availability, and
   `avp cm check <id|file>`. Read the actual error before changing configuration.
2. Find saved evaluations with `avp eval list`; outputs live under
   `~/.avp/runs/` (or `AVP_HOME/runs/`). Inspect the trajectory and launch logs.
3. Compare the requested Commission with `agent_described` capabilities and the
   effective tools and asset status recorded by `agent_started`.
4. Read `error_occurred`, tool results, and the final `agent_stopped` reason.
   Distinguish launch/auth failures, unsupported capabilities, adapter failures,
   and an agent that ran successfully but failed the task or scorer.
5. Sum per-response `assistant_message` usage and cost. Never add cumulative
   runtime/thread totals again. A model turn is not a conversational user turn.

The [Trajectory spec](avp/core/spec/v0.1/trajectory.md) defines event payloads,
ordering, span relationships, and accounting. All agent events use the
CloudEvents envelope and `source: avp://agent`.

## Adapt an existing runtime

Work in a source checkout and follow its `AGENTS.md`. Start from the
[adapter guide](https://github.com/portofcontext/agent-voyager-project/blob/main/agents/_template/README.md)
and [integration patterns](https://github.com/portofcontext/agent-voyager-project/blob/main/PATTERNS.md).

1. Scaffold with `make new-agent NAME=avp-<sdk>` or `make new-agent-rust NAME=avp-<sdk>`.
   Replace the scripted harness with the runtime that owns the model/tool loop.
2. Map Commission fields to native configuration and describe the runtime's
   actual built-ins and supported capabilities. Use shared preflight checks and
   the stock `ping`, `describe`, and `run` entrypoint.
3. Import wire types from `avp.commission`, `avp.descriptor`, and `avp.trajectory`.
   Translate native responses and tool results into Recorder reports. Preserve
   response boundaries, call IDs, content, and per-response usage. Normalize
   SDK-specific duplicate notifications in the adapter; propagate invalid
   Recorder reports instead of silently discarding them.
4. Leave workspace, home, credentials, and session-state provisioning to the
   launcher. Stock entrypoints honor `AVP_WORKSPACE`; library calls inherit
   their caller's context.
5. Test the native-event-to-Recorder path, then run live conformance for the
   adapter with `avp-conformance check --agent <manifest> --suite v0.1`.
   Report capability skips alongside passes: skipped behavior was not tested.
   Consult [conformance coverage](https://github.com/portofcontext/agent-voyager-project/blob/main/avp/core/conformance/src/avp_conformance/COVERAGE.md)
   before claiming support. Follow the checkout's required verification commands.

Use the [Agent Descriptor spec](avp/core/spec/v0.1/agent-descriptor.md) for
capability declarations and the [spec index](avp/core/spec/v0.1/README.md) for
schemas and examples. If a requested behavior is outside v0.1, identify that
boundary explicitly; do not invent wire fields or supervisor callbacks.
