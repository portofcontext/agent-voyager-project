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
make sync                       # from the repo root: installs the workspace

uv run avp init                 # pick a benchmark (try 'demo'): writes an eval here + commissions to ~/.avp
uv run avp eval run <config>    # run it against a real agent, print the board; iterate
uv run avp eval view            # open the most recent run on agentvoyagerproject.com
```

Or use the Make passthrough: `make avp init`, `make avp eval list`.

**Credentials.** Each agent runs as a subprocess that inherits your environment
and resolves its own credentials, exactly as it would standalone. Set up whatever
your chosen agent expects (for an Anthropic-backed run, `export
ANTHROPIC_API_KEY=...`; Goose also honors `GOOSE_PROVIDER` + that provider's key).
The CLI reads no keys and assumes no provider.

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
  `avp commission list` shows them all. Run outputs live under `~/.avp/runs/`
  (delete one with `avp eval delete <id>`, or all with `avp eval delete --all`).

## The eval config (no code)

An eval is one JSON file that references commissions by id. `avp init` scaffolds
it; you edit it; the CLI runs it.

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
  "model": "claude-haiku-4-5",
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
  `run_id`/`supervisor` are assigned per run. `avp commission describe <id>` prints the
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
| `avp eval view [ID]` | open an eval on agentvoyagerproject.com (default: most recent run) |
| `avp eval delete ID [--all]` | delete one recorded run by id (or `--all` for every run, `~/.avp/runs`) |
| `avp commission list` | list your portable commission library (`~/.avp/commissions`) |
| `avp commission describe ID` | render the Commission a library commission yields |
| `avp commission check ID\|FILE` | check a library commission by id (or a wire Commission JSON file) |
| `avp commission delete ID` | remove a commission from your library |
| `avp agent list` | the agents you can run against + whether each is ready |
| `avp agent describe NAME` | one agent's capabilities: tools, models, skills, MCP (`--json` for raw) |

Run flags (`run` / `demo`): `--agent goose,claude-code` (compare agents),
`--model <id>` (override every commission's model), `--json out.json` (machine-readable
board + per-run trajectory pointers), `--threshold T`, `--max-items N`, `--quiet`.

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

## Visualize a run

Every run writes a raw NDJSON trajectory under `--out` (a temp dir by default;
the board prints the path). `avp show <trajectory>.ndjson` gives you two views,
both offline:

- **Terminal (default)** — a colored event voyage right in your shell: the
  run's stats line plus each event as a brand-colored dot with its label (tool
  name, stop reason, per-turn tokens). No browser.
- **`--web`** — the full **constellation** from agentvoyagerproject.com (events
  as stars on a voyage curve, revealed in sequence) as a self-contained HTML
  file it opens in your browser (`--no-open` to just write it, `--out file.html`
  to place it). No server, no network.

## Outputs

Every `avp eval run` ends with a **voyage id** (e.g. `swift-harbor`) and writes
the eval's data. The CLI produces the data; the site renders it. A benchmark post
is: run the eval → view it → write.

- **the voyage id** — a short, memorable handle for the run, printed when it
  finishes. `avp eval view <id>` opens it on the site; `avp eval list` shows recent
  ids. (Bare `avp eval view` opens the latest, no id needed.)
- **`trajectories.json`** — the whole eval in the `by_commission` shape
  [agentvoyagerproject.com](https://agentvoyagerproject.com) renders (keyed by
  commission, each carrying every run's full AVP trajectory, plus a `commissions`
  block of each one's config). `avp eval view` opens it; or drop it into the site.
  One file per agent when you compare several.

## How it works

`avp eval` drives any conforming AVP agent through the same contract the
conformance harness uses: `<agent> run --commission <file> --out <ndjson>`,
declared in the agent's `avp-conformance.json`. For each commission/item it loads
the config, composes a Commission, runs the agent, reduces the trajectory, extracts
the final answer, scores it by the named scorer, and ranks a `Board`.

Layout:

```
src/avp_cli/
  cli.py            # the `avp` umbrella: init / eval / commission (rich output)
  paths.py          # the ~/.avp asset root (AVP_HOME): commissions/ + runs/
  library.py        # the portable commission library (~/.avp/commissions/<id>.json)
  config.py         # load an eval JSON config -> internal engine (the config-not-code seam)
  commission.py     # inspect a Commission a library commission yields (show / validate)
  console.py        # rich Console + stdout(results)/stderr(progress) discipline
  brand.py          # the AVP ship logo + palette for the terminal
  viz.py            # trajectory -> standalone HTML constellation (avp show)
  agent.py          # run_agent: the `run --commission --out` manifest contract
  agents.py         # the goose / claude-code registry + preflight
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

The CLI is its own example: `uv run avp init capitals` scaffolds the bundled
capitals eval and `uv run avp eval run capitals.eval.json` runs it end-to-end
against a real agent. For agent-side integration examples (the drop-in
`AVPClaudeSDKClient`), see `agents/avp-claude-agent-sdk/python/`.
