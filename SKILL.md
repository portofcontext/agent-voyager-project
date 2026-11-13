---
name: avp
description: >
  Set up and use AVP (Agent Voyager Project) to run agents, configure Commissions,
  compare agents or prompts with evaluations, and inspect trajectories. Use when
  onboarding to AVP, debugging an AVP run, or adapting an existing agent runtime
  to the Commission, Agent Descriptor, and Trajectory specs.
---

# Agent Voyager Project

A supervisor sends one Commission; the agent's existing runtime does the work
and streams its Trajectory. There is no mid-run supervisor push channel.
Read the [spec overview](spec/v0.1/README.md) before constructing wire objects.

## Run an agent

1. Inspect the installed CLI's `--help`. The rebuilt v0.1 CLI currently needs a
   repository checkout and uses OpenSandbox with a Docker-compatible container
   engine. From the checkout, use `uv run --project avp-cli avp`.
2. Install an adapter image with `avp agent install <name> <Dockerfile> --context
   <repository-root>`. SDK dependencies are still local to the repository.
   Use `avp agent list`, `ping`, and `describe` to inspect the installed agent.
3. Store a model key with `avp vault set <name>`, which prompts locally. Never
   request secret values in chat or write them into a Commission. Reference it
   as `model.credential: {"proxy": "<name>"}`. For environment references, pass
   the named variable with `--env NAME` or `--env-file`.
4. Write a Commission file following the [Commission spec](spec/v0.1/commission.md).
   Required fields are `avp_version`, `run_id`, `model`, and `prompt`. The model
   is an object with `provider` and `id`. Choose a fresh run ID for each dispatch.
5. Run `avp run --agent <name> --commission <file>`. Real provider calls cost money.
   Report the outcome and the saved Trajectory location. Inspect errors before
   retrying a failed run.

Agent-specific built-in settings live under `agents`, keyed by the Descriptor's
`agent_name`. Omitted allowlists allow all built-ins; `[]` allows none. The
Commission adds its own MCP servers and skill files alongside built-ins.
`system_prompt` replaces the runtime's prompt. `output_schema` describes an object.
Read the spec rather than guessing unsupported settings.

## Evaluate and inspect

In the checkout, read `avp-cli/docs/eval.md` for the current eval format. Evals
specify `eval_version`, `name`, `commission`, `dataset`, and `scorer`, and select
installed agents in the file or through `--agent`. The built-in scorers are
`match` and `command`. Use `avp eval run`, `list`, and `show` to run comparisons
and inspect results. Saved Commissions and the TUI are not implemented yet.

Compare correctness, cost, and response counts separately. Preserve the run's
Commission and Trajectory as evidence. Reduce per-response usage and cost once;
do not add runtime totals or count subagent usage twice. See the
[Trajectory spec](spec/v0.1/trajectory.md). File runs save Commission, Descriptor,
and [Agent Start](spec/v0.1/agent-start.md) alongside the ATIF trace. Agent Start
contains resolved configuration and full skill contents. Keep the four documents
and any ATIF-referenced image files together when moving a run.

## Integrate a runtime

In a checkout, read `avp-sdk/README.md` and a migrated adapter's README. The SDK
provides types, Recorder, run plan, pricing, endpoints, and agent command line.
The runtime still owns its loop. Describe only its actual built-in capabilities,
using the [Agent Descriptor spec](spec/v0.1/agent-descriptor.md).

Test native event translation into a Trajectory, install the adapter's image,
check `ping` and `describe`, and run `avp conformance check`. Report passes and
capability skips together. Use the adapter's real-model checks after changes to
runtime integration. Keep unsupported behavior explicit in its Known gaps.
