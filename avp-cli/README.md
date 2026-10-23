# avp-cli

`avp` is the local AVP CLI; this package (`avp-cli`) provides it. The fastest way
to **build, run, and iterate on AVP Commissions**, where an **eval is a JSON
config file, not code**. You author *commissions* (one agent configuration each:
a prompt, a tool surface, skills, a model, an output schema) as portable files in
your library, write a short eval that references them by id, run them over a
dataset against a real agent (Goose or Claude Code), and get a ranked board:
**accuracy, pass-rate, $/run, turns/run**. The trajectories are real AVP, and the
config is the same artifact that rides `pctx` to the cloud.

```
        avp eval · capitals-extraction · 3 items · agent=goose
┏━━━┳━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┓
┃ # ┃ commission┃ accuracy ┃ pass_rate ┃   $/run ┃ turns/run ┃
┡━━━╇━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━┩
│ 1 │ few-shot  │     100% │      100% │ $0.0008 │       2.0 │
│ 2 │ terse     │      83% │       67% │ $0.0006 │       1.7 │
│ 3 │ baseline  │      50% │       33% │ $0.0004 │       1.3 │
└───┴───────────┴──────────┴───────────┴─────────┴───────────┘
```

Notice rank 2: 83% accuracy but only 67% pass_rate. Accuracy is the mean per-item
score (partial credit); pass_rate is the share of items that fully cleared the
bar. They measure different things, and a good benchmark reports both.

## Quickstart

```bash
uv tool install avp-cli         # installs the `avp` command (or: pipx install avp-cli)

avp agent install --all            # every built-in agent, at this CLI's versions
avp env secret create anthropic    # prompts for your API key
avp init capitals --agent claude-code
for id in capitals-baseline capitals-few-shot; do
  avp cm create "$id" --from "$id" --force --provider-id anthropic --credential anthropic
done
avp eval run capitals.eval.json    # paid model calls; prints the ranked board
avp eval share           # upload the most recent run, print a short link
```

Contributors working in the repo: `make sync && source .venv/bin/activate`
(then use `avp …`).

**Docker is required for the default runtime.** Agent runs execute inside an
[OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) container; the
CLI manages the rest itself (a local control-plane server under
`~/.avp/opensandbox/`, derived images, egress policy). Have Docker Desktop,
OrbStack, or colima running and you're set; the first run pulls/builds images
and is slower, every later run reuses them. `avp sandbox status` shows the
stack's health.

To run installed agents directly in the current environment, select `local`:

```bash
avp eval run capitals.eval.json --runtime local
```

The local runtime needs no Docker and adds no OS isolation. It inherits any
outer container or VM boundary and each agent's native restrictions. Use it for
trusted local work or inside an environment that already provides confinement.
The CLI gives each agent run fresh home and SDK state directories, saves its
workspace and trajectory, and terminates its process group on exit or timeout.
Local processes inherit the caller's environment. The launcher overrides its
workspace and state directories; manifest settings and explicit Commission
provider routing take precedence over inherited values.
Detached processes are not contained. It records the selected runtime in
`run.json`; resuming with a different runtime is refused.

Run commands also accept `AVP_RUNTIME=local`; an explicit `--runtime` wins.
There is no automatic fallback when Docker fails. The local environment accepts
`paths`, `files`, and `setup`. Container `image`, `packages`, `net`, and `resources`
settings are rejected: install dependencies in the current environment instead.
Setup commands run in the saved workspace and count toward the run timeout.
Agent commands bootstrap in their manifest directory; stock entrypoints then
enter `AVP_WORKSPACE`. Relative stdio MCP commands resolve in that workspace.

The optional `libkrun` runtime supports offline runs only. Networked runs fail
closed until filtered egress is supported; use the default `opensandbox` runtime
when a Commission or environment requires network access.

## Model authentication

Store an API key for the provider used by your Commission's model. Each command
prompts for the key:

| Provider | Create a key | Store it |
|---|---|---|
| OpenAI | [OpenAI dashboard](https://platform.openai.com/api-keys) | `avp env secret create openai` |
| Anthropic | [Claude Console](https://platform.claude.com/settings/keys) | `avp env secret create anthropic` |
| Google | [AI Studio](https://aistudio.google.com/apikey) | `avp env secret create google` |

`avp env secret list` shows stored names without revealing their values. Keys
live in `~/.avp/secrets.toml`, a plaintext file readable only by your user.

Reference the stored key when creating a Commission:

```bash
avp cm create my-task --agent claude-code --provider-id anthropic --credential anthropic
avp run --agent claude-code --commission my-task "Say hello"
```

For an existing Commission, add this provider field to its JSON:

```json
"provider": {"id": "anthropic", "credential": {"vault": "anthropic"}}
```

Storing a key does not attach it automatically. The [quickstart](#quickstart)
shows how to attach it to both sample Commissions using the CLI.

Models use `origin/model` slugs. Codex uses OpenAI; Claude Code uses Anthropic.
Pi and other multi-provider agents use the selected model's provider.
`avp agent describe <name>` lists the adapter's capabilities. Keys need access
and quota for that model; runs use provider API billing.

### Credential routing

The host-side broker resolves the stored key and adds it to provider requests.
The launched agent receives a per-run token; the actual key stays out of
Commissions and container files. With `--runtime local`, agents can access the
host filesystem, including the credential store.

**MCP servers with OAuth.** Run `avp env secret login <handle> --url <mcp-url>`
once to sign in through your browser, then set `"auth": {"vault": "<handle>"}`
on the server in the Commission. The login is stored on the host in
`~/.avp/oauth/` and the broker refreshes the token during runs, so the agent
never sees it. Servers without dynamic client registration need
`--client-id` (and `--client-secret`) for a client you registered yourself.

## Where things live

Two kinds of artifact, two homes:

- **The eval file** is authored **in place**, in your project (`avp init` writes
  `<key>.eval.json` to the current directory). It's short, you edit it, you commit
  it. It says *what to compare over what, scored how* — and references commissions
  by id.
- **Commissions** are **portable** artifacts in your library at
  `~/.avp/commissions/<id>.json` (override the root with `AVP_HOME`). Each file is a
  **raw AVP wire `Commission`** and nothing else — no tool-specific fields — so the
  same artifact the CLI runs is what the cloud consumes. The id is the filename;
  the eval engine fills `{input}` and assigns `run_id`/`supervisor` per run.
  `avp cm list` shows them all. Run outputs live under `~/.avp/runs/`
  (delete one with `avp eval delete <id>`, or all with `avp eval delete --all`).

## The eval config (no code)

An eval is one JSON file that references commissions by id. `avp init` scaffolds
it; you edit it; the CLI runs it. The format is pinned by
[`eval.schema.json`](./eval.schema.json) plus the normative rules in
[`EVAL-FORMAT.md`](./EVAL-FORMAT.md) (templating, identity vs locator keys,
run stamping) — the contract a cloud runner reproduces.

```json
{
  "name": "capitals-extraction",
  "dataset": {
    "source": "inline",
    "items": [
      { "id": "paris", "prompt": "Paris is the capital of France; ~2M people.",
        "expected": { "city": "Paris", "country": "France", "population_millions": 2 } }
    ]
  },
  "scorer": { "name": "structural-match", "threshold": 1.0 },
  "commissions": ["baseline", "terse", "few-shot"]
}
```

A commission file (`~/.avp/commissions/terse.json`) is a **raw AVP wire
`Commission`** — the same shape an agent runs:

```json
{
  "schema_version": "0.1",
  "run_id": "terse",
  "model": "anthropic/claude-haiku-4-5",
  "prompt": "Return ONLY JSON {city,country,population_millions}: {input}",
  "output_schema": { "type": "object", "properties": { "city": { "type": "string" } } }
}
```

- **`commissions`** (in the eval) — a list of ids (filenames in your library). To
  A/B one change, copy a commission to a new id, change just that field, and add
  the id here, so the board isolates its effect.
- **a commission file** — a wire `Commission` (`avp.commission.Commission`): real
  fields only (`prompt`, `system_prompt`, `model`, `enabled_builtin_tools`,
  `skills`, `mcp_servers`, `output_schema`, `tags`, …). The id is the filename, not
  a field. `{input}` in `prompt` is a plain string the eval fills per case;
  `run_id`/`supervisor` are assigned per run. `avp cm describe <id>` prints the
  full Commission (nulls included) so you learn the real wire shape.
- **`scorer`** — built into the CLI, chosen by name + params:
  - `exact-match` — answer text equals `expected` (normalized).
  - `structural-match` — fraction of `expected` dict keys the JSON answer got right; `threshold` decides pass.
  - `structural-fidelity` — directional HTML fidelity vs a reference (ParseBench-style); needs the `parsebench` extra.
- **`dataset.source`** — referenced, never loaded by your code:
  - `inline` — `items: [{id, prompt, expected}]`.
  - `file` — `path` to a `.jsonl`/`.json`; either rows already `{id,prompt,expected}`, or an `input` template + `expected_field` mapping.
  - `huggingface` — `id` + `split`, an `input` template over row fields, `expected_field`, `id_field`; needs the `huggingface` extra.

## `avp init` — the catalog

`avp init` opens a picker; `avp init <key>` scaffolds directly. Each entry writes
an eval file in place and installs its commissions into your library (an id you
already have is left untouched):

- **`capitals`** — the tiny capitals extraction above (the default off a
  non-interactive terminal). Inline data, no extra deps, runs for pennies.
- **`parsebench`** — PDF pages → HTML over the real
  `llamaindex/ParseBench` dataset, scored on structural fidelity. Needs
  `uv sync --extra parsebench`.
- **`custom`** — a minimal real eval you fill in with your own task and commissions.

## Commands

| Command | Does |
|---|---|
| `avp` | getting-started + agent routing |
| `avp init [key] [--dir D]` | scaffold an eval (in place) + its commissions (to the library) |
| `avp eval run CONFIG` | run a config, print the ranked board |
| `avp eval list` | list recent eval runs by voyage id (newest first) |
| `avp eval share [ID]` | upload an eval and print a short agentvoyagerproject.com link that lasts 30 days (default: most recent run) |
| `avp eval unshare [ID]` | take a shared eval's link down |
| `avp eval delete ID [--all]` | delete one recorded run by id (or `--all` for every run, `~/.avp/runs`) |
| `avp cm create ID --agent A` | generate a complete commission (full tool/skill surface + version pin); edit the JSON |
| `avp cm list` | list your portable commission library (`~/.avp/commissions`) |
| `avp cm describe ID` | render the Commission a library commission yields |
| `avp cm check ID\|FILE` | check a library commission by id (or a wire Commission JSON file) |
| `avp cm delete ID` | remove a commission from your library |
| `avp agent list` | the agents you can run against: whether each is installed and ready |
| `avp agent install --all` | install every built-in agent from its avp release |
| `avp agent install NAME [--manifest PATH \| --as NAME --from DIR]` | install one built-in agent, your own agent from its manifest, or a local build under its own name |
| `avp agent describe NAME` | one agent's capabilities: tools, models, skills, MCP (`--json` for raw) |
| `avp agent uninstall NAME` | remove an installed agent from `~/.avp/agents` |
| `avp run "TASK" --agent A [--env E] [--commission ID]` | commission an agent to do a task in a sandbox; `--commission` runs a library Commission with the task as its `{input}` |
| `avp env create NAME` | create an environment (`--image`/`--apt`/`--pip`/`--path`/`--file`/`--setup`/`--net`/`--cpu`/`--memory`) |
| `avp env list` | list your environments (`~/.avp/environments`) |
| `avp env show NAME\|PATH` | what an environment's sandbox world contains |
| `avp env run NAME -- CMD` | run a command inside an environment's sandbox |
| `avp env delete NAME` | remove an environment |
| `avp sandbox status` | Docker + managed-server health, live sandbox count |
| `avp sandbox stop` | stop the managed sandbox server |

Eval-run flags (`eval run`): `--agent goose,claude-code` (compare agents),
`--model <id>` (override every commission's model), `--env <name\|path>` (run agents inside an
environment), `--json out.json` (machine-readable board + per-run trajectory pointers),
`--threshold T`, `--max-items N`, `--quiet`.

**Live progress.** In a terminal, each run animates on one line as it sails: a
growing voyage of brand-colored glyphs (`●` model turns, `◆` tool calls) with a
live turn count, current tool, and running cost; finished runs collapse to a
one-line summary, so scrollback stays one line per run, not one per event.
Press **Ctrl-C** to stop the matrix early; you still get a board of the runs that
finished (marked stopped-early). `--quiet` or a non-terminal (piped / CI) falls
back to plain one-line-per-run logging.

**Comparing agents.** Pass `--agent goose,claude-code` and the run goes
task-major: both agents run each item back-to-back, a `⚖` head-to-head prints
the moment they both finish a task, and at the end you get one board per agent
plus a head-to-head table (commissions × agents, each agent's mean accuracy and
$/run in the caption). Cheap way to see, e.g., that one agent matches another's
accuracy at a fraction of the cost.

## Agents: install + local dev

A run uses an installed agent, by name. Start with every built-in agent:

```bash
avp agent install --all          # skips ones already installed; --force reinstalls
avp agent list                   # each agent, where it came from, and readiness
```

`avp agent list` shows where each agent's code came from:

- **avp release**: a built-in agent (`claude-code`, `codex`, `openai-agents`,
  `goose`, `pi`, `gemini-cli`, `deep-agents`, `pydantic-ai`, `opencode`) from
  a GitHub release, at the version this CLI pins. `avp agent install <name>`
  installs one, and `--version` picks another release. These names are
  reserved for the built-in agents.
- **manifest**: your own agent, installed by name from its
  `avp-conformance.json`. The manifest needs a `container` block
  (`{"install": ["<Dockerfile RUN step>", ...], "command": ["<argv>", ...]}`),
  for container runs. `--runtime local` uses the installed host command.
- **local build**: a built-in agent built from your checkout, installed under
  its own name so a board never mistakes it for the release.

```bash
avp agent install my-agent --manifest ~/work/my-agent/avp-conformance.json
avp run --agent my-agent "..."
```

Every agent release carries an `avp-release.json` saying how the agent
installs and runs, and the CLI follows it. A binary agent (goose) installs a
prebuilt executable; a Python agent (claude-code, codex, openai-agents,
deep-agents, pydantic-ai) installs into a managed venv (needs `uv`) at the
hash-checked dependency versions the release was tested with, so a new upstream
release can't break it; a Node agent (pi, gemini-cli, opencode) extracts its
package archive and runs with the host's `node`. Release downloads go over
plain HTTPS, so a public repo needs no auth; set `GH_TOKEN` only for a private
fork or to avoid API rate limits. The host install serves `avp agent describe`
(the free pre-flight view); actual runs install the agent's **Linux build into
the sandbox image**, so run-time dependencies (e.g. the claude-code agent's
Node + `claude` CLI) live in the image, not on your machine. Set
`AVP_AGENT_REPO` to install releases from a fork; the host install and the
sandbox image both come from it.

**Testing your own build of a built-in agent (no release needed).** Build it
into a directory laid out like its release, check it runs, and install it
under a `-dev` name:

```bash
make build-agents AGENTS=claude-code    # dist/agents/claude-code/: artifacts + avp-release.json
make smoke-agents AGENTS=claude-code    # runs it in its sandbox image against a stub model
avp agent install claude-code --as claude-code-dev --from dist/agents/claude-code
```

The directory is copied into the sandbox image, so `--agent claude-code-dev`
runs your build, and boards and run manifests label it as a local build. The
goose binary runs in the sandbox only when built on Linux. A custom agent needs
no build step at all: install its manifest, or pass a manifest path to
`--agent` for a one-off run.

## Environments + `avp run`

An **environment** is a CLI-side asset (the AVP spec never sees it) describing
the container world an agent runs in: a base image, packages, seeded
files/dirs, setup commands, an egress allowlist, and resource caps. Nothing
comes from the host machine; everything the agent sees is declared. It lives at
`~/.avp/environments/<name>.json`.

```bash
avp env create datasci \
  --image python:3.12-slim --pip pandas \
  --path ./my-repo \                 # copy a real codebase in (skips .git/node_modules/caches)
  --file TASK.md=@./task.md          # seed a file inline, or from a local path with @

avp env show datasci
avp env run datasci -- python -c "import pandas; print(pandas.__version__)"   # a command
avp run --agent goose --env datasci "Do the task described in TASK.md"          # an agent
```

With the default runtime, `avp run` compiles the env + the agent's container recipe into a derived image
(`avp-env:<content-hash>`, built once, then cached), seeds the workspace on the
host, boots a sandbox with the workspace bind-mounted, runs `setup`, then
commissions the agent. The trajectory streams live; the workspace persists
under `~/.avp/runs/<id>/workspace` so you can inspect what changed. The
container is the write boundary, and the network is a default-deny egress
allowlist (model-provider APIs + GitHub + the env's `net`).

Block fields: `image` (default `python:3.12-slim`), `packages`
(`{apt: [...], pip: [...]}`, baked into the image), `paths` (dirs/files copied
into the workspace fresh each run), `files` (inline or `@local`), `setup`
(commands run in the sandbox workspace before the agent; network access needs
`net`), `net` (extra egress domains), `resources` (`{cpu, memory}`).
`avp eval run --env <name>` runs a whole eval inside the same environment (one
workspace shared across cells, one fresh sandbox per cell).
With `--runtime local`, each cell instead gets fresh local SDK state; the seeded
workspace is still shared across cells.

## Outputs

Every `avp eval run` ends with a **voyage id** (e.g. `swift-harbor`) and writes
the eval's data. The CLI produces the data; the site renders it. A benchmark post
is: run the eval → share it → write.

- **the voyage id** — a short, memorable handle for the run, printed when it
  finishes. `avp eval share <id>` uploads it and prints a short link; `avp eval list`
  shows recent ids. (Bare `avp eval share` shares the latest.) Sharing uploads the
  run's prompts, replies, and tool inputs and outputs; links expire after 30 days,
  and `avp eval unshare <id>` takes one down sooner.
- **`trajectories.json`** — the whole eval in the `by_commission` shape
  [agentvoyagerproject.com](https://agentvoyagerproject.com) renders (keyed by
  commission, each carrying every run's full AVP trajectory, plus a `commissions`
  block of each one's config). `avp eval share` uploads it.
  One file per agent when you compare several.

## How it works

`avp eval` drives any conforming AVP agent through the same contract the
conformance harness uses: `<agent> run --commission <file> --out <ndjson>`,
declared in the agent's `avp-conformance.json` — executed inside an OpenSandbox
container built from the env's derived image by default, or as a local subprocess
with `--runtime local`. For each commission/item it
composes a Commission, boots a fresh sandbox (workspace + io dirs
bind-mounted), runs the agent, reduces the trajectory, extracts the final
answer, scores it by the named scorer, and ranks a `Board`.

Layout:

```
src/avp_cli/
  cli.py            # the `avp` umbrella: init / eval / cm / agent / run / env / sandbox
  paths.py          # the ~/.avp asset root (AVP_HOME): commissions/ + runs/ + agents/
  library.py        # the portable commission library (~/.avp/commissions/<id>.json)
  config.py         # load an eval JSON config -> internal engine (the config-not-code boundary)
  commission.py     # inspect a Commission a library commission yields (show / validate)
  console.py        # rich Console + stdout(results)/stderr(progress) discipline
  brand.py          # the AVP ship logo + palette for the terminal
  viz.py            # trajectories -> agentvoyagerproject.com payload + share API (avp eval share)
  osb.py            # the managed OpenSandbox control plane (config, spawn, egress policy)
  images.py         # env + agent recipe -> cached derived image (avp-env:<hash>)
  environment.py    # the env spec (image/packages/paths/files/setup/net/resources) + seeding
  agent.py          # run_agent: the file contract through container or local launch
  agents.py         # built-in agents (agents.json) + resolution of installed agents
  release_manifest.py  # avp-release.json: how a release installs + its sandbox image recipe
  agent_install.py  # `avp agent install`: avp releases, custom manifests, local builds
  observability.py  # summarize: reduce a trajectory to per-run facts
  onboarding.py     # the WELCOME / agent-routing text
  state.py          # recent-run history under ~/.avp/runs (eval list / view / clear)
  catalog/          # avp init catalog: {eval, commissions} docs (parsebench / demo / custom)
  eval/             # the engine (internal)
    setup.py        #   Setup: one commission (id + Commission template; internal type)
    dataset.py      #   Dataset / Item
    scoring.py      #   scorers + FinalOutput / Score
    engine.py       #   run_eval, extract_final_output, RunResult, Board
    report.py       #   board_table (rich) + dump_json
```

The CLI is its own example: `avp init capitals` scaffolds the bundled
capitals eval and `avp eval run capitals.eval.json` runs it end-to-end
against a real agent. For agent-side integration examples (the drop-in
`AVPClaudeSDKClient`), see `agents/avp-claude-agent-sdk/python/`.
