# avp command tree

The design for the new `avp` CLI. Commands not built yet raise
NotImplementedError.

## Decisions

- Every agent runs in a sandbox, and OpenSandbox is the only sandbox for now.
  Docker, podman, or the local machine can be added later.
- OpenSandbox needs a container engine with the Docker API: Docker, OrbStack,
  colima, or podman through its Docker socket. The CLI uses that API (found
  through `DOCKER_HOST` or the default socket) to build images, and never runs
  the `docker` or `podman` commands.
- Credentials go through OpenSandbox's Credential Vault. The CLI looks up each
  secret and writes it to the sandbox's vault; it runs no proxy of its own.
- An agent is an image whose ENTRYPOINT is an AVP agent command line: it
  answers `ping`, `describe`, and `run --commission --out`. Its Dockerfile says
  how it installs; avp knows nothing about the agent's language or packages.
- `agent` manages agents; `sandbox` manages only the OpenSandbox service they
  run on. `--agent` takes an installed agent's name.
- Commands use the AVP terms: `describe` returns the Agent Descriptor.
- Built with Typer.
- `conformance` and `eval` share one engine. Each item writes a Commission for
  an agent, the engine runs it in a sandbox, and the item scores the run.
  Conformance cases are items defined in avp; an eval file's items are defined
  by users. See Conformance.
- Each command takes `--verbose`, which prints more about what avp does to
  stderr and never a secret's value. ⬜ Only the `vault`, `sandbox`, `agent`,
  `run`, and `conformance check` commands have it so far.

## Commands

✅ built, ⬜ not yet. A run keeps its Commission, Trajectory, and the agent's
stderr in `~/.avp/runs/<time>-<run_id>/`.

```text
avp                     ⬜ In a terminal, opens the TUI. Otherwise, and with --help, prints help.
│     avp [--eval RUN_ID | --run RUN_ID]
├── ✅ run               Run one agent on one Commission and write its Trajectory.
│     avp run --commission task.json --agent pd [--env NAME=VALUE | NAME] [--env-file .env]
│         [--allow-host pypi.org] [-v ./testing/mcp:/mcp:ro] [--out traj.ndjson] [--timeout 30m]
│     The agent's environment has only the variables --env and --env-file give. It can
│     reach only the model's host (model.base_url, or avp's default for the provider),
│     the Commission's HTTP MCP servers, and the hosts --allow-host adds. --volume
│     (-v) mounts a host path, read-write unless it ends in :ro. A {"proxy": NAME}
│     credential comes from `avp vault`, and the sandbox's Credential Vault adds it, so the
│     agent never sees it: model.credential to requests to the model's host, and an HTTP
│     MCP server's headers to requests to the server's host. ⬜ --out, --timeout.
│
├── eval              Run datasets against agents and Commissions, and score the results.
│   ├── ✅ run  Run an eval file and print the scoreboard. Each agent is described once first,
│   │           and each run goes in its own sandbox, as `avp run` runs it. The eval's runs,
│   │           results.json, and agents' Descriptors go in ~/.avp/evals/<time>-<name>/.
│   │           --env, --env-file, --allow-host, and -v apply to every run. --threshold exits 1
│   │           when accuracy is below it. Ctrl-C deletes the sandboxes still running and keeps
│   │           the finished runs' results. ⬜ --model, --resume.
│   │     avp eval run capitals.eval.json [--agent pd --agent my-agent] [--concurrency 1]
│   │         [--env NAME=VALUE] [--allow-host pypi.org] [-v ./data:/data:ro]
│   │         [--max-items 20] [--threshold 0.8] [--model openai/gpt-5-mini] [--resume RUN_ID] [--json]
│   ├── ✅ list List past eval runs, the latest first.
│   │     avp eval list [--limit 20]
│   ├── ✅ show Print a past eval's scoreboard and failed runs, as `eval run` prints them
│   │           at the end, with the same code. --json prints its results for scripts.
│   │     avp eval show [RUN_ID] [--agent pd] [--json]
│   ├── ✅ delete  Delete past eval runs and their runs' directories. Asks first; --yes
│   │           (or --force) doesn't, and is needed without a terminal.
│   │     avp eval delete RUN_ID... | --all [--yes]
│   ├── ⬜ share   Later, not a priority. Upload an eval's results and Trajectories to
│   │           agentvoyagerproject.com and print a link that lasts 30 days, as the old CLI's
│   │           `eval share` does. The upload holds every run's prompts, replies, and tool
│   │           inputs and outputs, so avp says so and asks before uploading.
│   │     avp eval share [RUN_ID]
│   └── ⬜ unshare Later, with share. Take a shared eval's link down before it expires.
│         avp eval unshare RUN_ID
│
├── conformance         Check that an agent follows the spec's rules for agents. See Conformance.
│   ├── ✅ check   Run the cases against an agent and report pass, fail, or skip by rule. The
│   │              runs are kept in ~/.avp/conformance/<time>-<agent>/. Exits 1 when a MUST case fails.
│   │     avp conformance check --agent pd [--rule commission.5.1] [--case agents-without-entry]
│   │         [--model anthropic/claude-haiku-4-5] [--concurrency 4] [--json]
│   │         [-v ./src:/app/src:ro] [--entrypoint "cargo run -q --"]
│   │         [--mock-image my/aimock:dev]
│   │     While developing an agent, -v mounts its code and --entrypoint changes how it
│   │     starts, in every sandbox the agent runs in, so no rebuild is needed.
│   │     --mock-image runs another aimock image for the mock model.
│   └── ✅ list    List the rules and the cases for each.
│         avp conformance list [--rule commission.5.1]
│
├── agent               Agents: an image whose ENTRYPOINT is an AVP agent command line.
│   ├── ✅ install    Build the agent's image, check it answers ping and describe in a
│   │                 sandbox, and save it. Installing over an agent replaces it. Shows
│   │                 each build step and check as it runs; --verbose prints the build.
│   │     avp agent install pd agents/avp-pydantic-ai/python/Dockerfile [--context .]
│   ├── ✅ list       List your agents.
│   │     avp agent list
│   ├── ✅ ping       Check that the agent starts in a sandbox, without loading it.
│   │     avp agent ping pd
│   ├── ✅ describe   Print the agent's Agent Descriptor, from its describe in a sandbox.
│   │     avp agent describe pd
│   └── ✅ uninstall  Remove an agent and its image.
│         avp agent uninstall pd
│
├── ⬜ commission        Commission files.
│   ├── new     Write a Commission for an agent, with its built-in items listed.
│   │     avp commission new --agent pd --model openai/gpt-5-mini [--prompt "..."] > task.json
│   └── check   Validate a Commission and apply the Commission checks for an agent.
│         avp commission check task.json [--agent pd]
│
├── vault               Secrets in the system's credential store (the macOS Keychain, Windows
│   │                   Credential Manager, or the Secret Service on Linux), for a Commission's
│   │                   {"proxy": NAME}. Names, descriptions, set times, and sign-in expiry, never values, are kept in ~/.avp/vault.json.
│   ├── ✅ set     Store a secret under a name a Commission can refer to; prompted when VALUE is omitted.
│   │     avp vault set anthropic [VALUE] [--description "Team key"]
│   ├── ✅ login   Sign in to an MCP server with OAuth in the browser, and store the access token,
│   │              the refresh token, and when the access token expires. Signing in again replaces them.
│   │     avp vault login linear --url https://mcp.linear.app/mcp [--scope read]
│   ├── ✅ refresh Get a new access token for a sign-in with its refresh token.
│   │     avp vault refresh linear
│   ├── ✅ list    List secrets' names, descriptions, when each was last set, and when a sign-in expires. --check reads each one to confirm it is still in the store.
│   │     avp vault list [--check]
│   └── ✅ delete  Delete a secret.
│         avp vault delete anthropic
│
└── sandbox             The OpenSandbox service every agent runs on.
    ├── ✅ start   Start the service. Agent commands also start it when needed.
    │     avp sandbox start
    ├── ✅ stop    Stop the service. ⬜ Stopping sandboxes still running.
    │     avp sandbox stop
    └── ✅ status  Show the container engine and where avp found it, and whether the service is running.
          avp sandbox status
```

## How an agent is installed and run

One agent is one image. OpenSandbox runs images but doesn't build them, so
the CLI builds the image itself and OpenSandbox starts a fresh sandbox from it
for each command, deleted when the command ends. Each sandbox starts idle, and
the CLI runs the image's ENTRYPOINT in it through OpenSandbox's exec daemon,
so it can fill the vault first and gets the command's exit code and output.
Everything that changes per run (the Commission, the workspace,
the credentials) reaches the sandbox at run time, never through the image.

## Eval

The eval file and its placeholders are in [the eval file guide](docs/eval.md).
`avp eval run` reads an eval file, checks it, runs it, and scores each run
with `match` or `command`.

- **Eval to EvalConfig.** `EvalConfig.from_eval` reads an eval file's Commissions,
  checks everything, and turns `scorer` into its callable. The `EvalConfig`
  yields each Commission × agent × item with that run's Commission built.
  Conformance will build an `EvalConfig` directly, with a case's check as
  the scorer.
- **One run, as `avp run` does it.** Each of an eval's runs goes through the
  same function as `avp run`, which sets up the sandbox, runs the agent, and
  keeps the run's directory. An eval's runs go under
  `~/.avp/evals/<time>-<name>/runs/<run_id>/`, one at a time unless
  `--concurrency` says more. A run whose agent never starts, such as one
  whose sandbox won't start, fails with a score of 0.
- **Scorers.** Inside avp, a scorer is a callable, plain or async, that takes
  the scorer's input and returns a score, both as the guide defines them.
  `match` and `command` are such callables; ⬜ conformance cases will be
  too, and later `structured-match` and `llm-judge`. Users add their own scorer with `command`,
  which gets the same input as JSON, so there is no Python plugin interface.

## Conformance

`avp conformance check` shows whether an agent follows the spec's rules for
agents, with no real model calls. The cases are in
`src/avp_cli/conformance/cases.py`. ⬜ Most cases so far end before a model call,
in `commission.5.1` and `commission.5.4`; `trajectory.4.1` has the first that
reaches the mock model.

- **Cases by rule.** A rule's ID is its spec and section number:
  `commission.5.3` is "Turned-off items are hidden and blocked", and
  `trajectory.4.5` is "Every tool call has a result". A rule can have several
  cases, since a section can hold several requirements. The cases cover the
  rules for agents: section 5 of the Commission spec, and section 4 of the
  Trajectory and Agent Descriptor specs. Rules for supervisors are avp's own,
  and avp's tests cover them. `conformance list` shows any rule still without
  a case.
- **Pass, fail, or skip.** A case is skipped, with the reason, when the agent's
  Descriptor says it lacks what the rule needs, such as subagents. The report
  lists passes and skips together.
- **The agent as shipped.** A case writes its Commission from the agent's real
  Descriptor and never patches the agent. `-v` and `--entrypoint` are for
  development, so a final check runs without them. A `conform` entrypoint that patches
  an agent to force a scenario is a future idea, for a scenario no Commission
  or mock can create.
- **No real model calls.** A case that needs a model lists its responses, once,
  in the format of [aimock](https://github.com/CopilotKit/aimock), which answers
  in the format of the provider `--model` names. When a selected case has
  responses, avp starts one aimock for the check, in its own OpenSandbox sandbox
  with no outbound access, from a published image pinned by digest
  (`--mock-image` runs another). The case's `model.base_url` points at it, so the
  agent needs no launch option and the spec defines nothing for it. A request no
  case scripted gets an error. A check costs nothing and needs no provider key,
  so it can run in CI.
- **One provider per check.** Each scenario is one case, and `--model` picks the
  provider, so a second provider is a second check. A check stops up front when
  the agent's `supported_models` rules out the model, and the mock serves
  Anthropic, Google, and OpenAI so far.
- **One engine with `eval`.** A conformance case is an eval item defined in
  avp: it writes a Commission from the agent's Descriptor, the engine runs it,
  and the case scores the run. Pass is a score of 1 and fail is 0. A skipped
  case never reaches the engine, and a run that didn't start, or that its scorer
  couldn't score, fails with the reason. Any line that isn't a valid event of a
  type the SDK knows fails the case. Conformance adds a rule and a level (MUST or
  SHOULD) to each item and groups its report by rule. The engine settings differ:
  conformance uses a stand-in credential and a `model.base_url` that is the mock
  model's or never resolves, and prints its report; an eval uses `avp vault`
  credentials and saves its results.

## TUI

⬜ `avp` with no arguments opens the TUI when stdin and stdout are a terminal.
In a pipe or CI it prints help, as `avp --help` always does. It is the CLI's
home screen, so it has no command name of its own; `dashboard` would suggest
read-only metrics, and `tui` names how it's built.

The TUI is a place to see what exists and act on it:

- **Explore:** Commissions, agents (with each one's Agent Descriptor), runs and
  their Trajectories, evals and their scoreboards, vault entries (names only),
  and the sandbox service's status. Each item links to related items: a run to
  its agent and Commission, an eval to its runs.
- **Act:** do from the TUI what the other commands do, such as writing a new
  Commission, starting a run or an eval, and installing or uninstalling an
  agent. The TUI calls the same code as those commands and adds no behavior of
  its own.
- **Step through a Trajectory:** move event by event through a run, from
  `run_requested` to `agent_stopped`: each model response with its usage and
  cost, each tool call next to its result, and subagents nested under the call
  that started them. Follow a run live while it streams.
- **Step through an eval:** start from the scoreboard, open an item to compare
  agents' runs side by side, and step into any run's Trajectory.
- **AVP themed:** the look and wording follow the voyager theme.

Options on `avp` open the TUI on one item: `avp --eval RUN_ID` on an eval's
scoreboard, and `avp --run RUN_ID` on a run's Trajectory. The TUI replaces
`eval view`. `eval show` stays, as plain terminal output for CI logs, SSH
sessions, and scripts (`--json`), and the TUI is for exploring.


## Open

1. Installed agents are state under `~/.avp/agents/`. An eval file could name
   a Dockerfile instead, to be committed with it.
2. Removing the saved-Commission library: `run --commission` takes a path.
3. Removing `init` and the catalog templates, for an example eval file in the docs.
4. Credential names: the default name a Commission uses for a model's key (the
   provider ID?), and whether a key already in the shell's environment counts.
5. What `run` prints, and where the Trajectory goes without `--out`
   (`~/.avp/runs/<run_id>/`?).
6. OAuth tokens in the Credential Vault: avp refreshes an expired token before
   a run, but the vault doesn't refresh it during one, so a run longer than
   the token lasts can lose access.
7. Installing the project's own agents by name and version, without a
   checkout, once the SDK and agents are published.
