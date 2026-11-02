# CLI plan 1: shared modules, then install and ping/describe

Goal: `avp agent install` builds an agent's image, and `ping` and `describe`
run in an OpenSandbox sandbox from it. No model calls, credentials, or network
yet; those are the next plan.

## Shared modules

Each concern lives in one place, so `run`, `eval`, and `conformance` never
repeat it. Built so far: `paths.py`, `console.py`, `engine/images.py`,
`sandbox/service.py` and `sandboxes.py`, and `agents/` (`cli.py`, `store.py`,
and `command.py`, which is the `launch.py` below).

| Module | Job | Plan 1 |
|---|---|---|
| `paths.py` | The `~/.avp` layout: agents, runs, secrets, the OpenSandbox service | Yes |
| `console.py` | One rich console, and how errors and progress print | Yes |
| `engine.py` | The container engine through the Docker API: check it's reachable, build an image from a Dockerfile and a context directory with progress, check an image exists, remove one | Yes |
| `agents.py` | Agent definitions: save and load them, resolve an `--agent` value, write the Dockerfile for one | Working copies only |
| `sandbox.py` | The OpenSandbox service (config, start, health, stop) and sandboxes (create from an image with mounts, environment, network policy, and later the credential proxy; delete) | No network, no vault |
| `launch.py` | The agent command line inside a sandbox: `ping`, `describe`, `run`, through a mounted run directory, with timeouts and, later, signals | `ping` and `describe` |
| `credentials.py` | Find a secret's value by name | Plan 2 |
| `commission.py` | What a Commission needs from the sandbox: allowed hosts, vault bindings, environment variables | Plan 2 |

## Plan 1 steps

Done: steps 1 to 6, with `create` named `install` and taking a Dockerfile, and the agent command
line's output read from the command's stdout rather than a mounted run
directory, which comes with `run`.

1. `paths.py` and `console.py`.
2. `engine.py`, with a test that builds and removes a tiny image. It is skipped
   when no engine answers.
3. `sandbox.py`: write the OpenSandbox 1.2 server config, start the service in
   the background, wait until it answers, stop it. Create a sandbox from an
   image with one mounted run directory and egress denied, and delete it.
   Wire up `avp sandbox start | stop | status`.
4. `launch.py`: run `<command> ping --out /io/ping.json` and
   `<command> describe --out /io/descriptor.json` in a sandbox, then read and
   validate the files (`{"type": "pong", "avp_version": "0.1"}`, then the SDK's `AgentDescriptor`).
5. `agents.py`: `agent create NAME --from <working copy>` writes the Dockerfile
   from the agent's manifest, builds the image, then pings and describes the
   agent and saves the definition with the image name. The Descriptor is never
   saved; `describe` asks the agent each time. Wire up
   `avp agent create | list | describe | delete`.
6. An end-to-end test: create a small fixture agent, describe it, delete it.
   Skipped when no engine answers.

## Decisions needed for plan 1

1. **A test agent.** Decided: migrate `avp-pydantic-ai` to the new SDK first.
   `ping` and `describe` need no model call, and it is the real agent plan 2
   uses for a model call through the Credential Vault.
2. **The agent manifest.** Decided: none. An agent is a Dockerfile whose
   ENTRYPOINT is its command line.
3. **Where `ping` lives.** Decided: `avp agent ping NAME`, possibly removed
   after testing.
4. **Agent definitions** as files or `~/.avp` state (open item 1 in
   COMMANDS.md). Plan 1 needs one; `~/.avp/agents/<name>.json` is simplest
   to start and can become a file you commit later.

## Later plans

- Plan 2: `run` with a real model call through the Credential Vault, plus
  `credentials.py`, `commission.py`, and the HTTPS trust check.
- Plan 3: `conformance check` on top of `launch.py`.
- Releases: install the project's own agents by name and version once they are
  published.
