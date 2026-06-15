# The Context Nuke — Code Mode x Arcade, measured on AVP

A reproducible demo of what Code Mode (pctx) does for an agent working over real,
messy data through Arcade-style tools, scored against ground truth.

The idea in one line: hand an agent a deliberately brutal spreadsheet and ask it
finance questions. A normal tool-calling agent reads the rows into its context
and guesses, badly and differently every run. The same agent reaching the same
sheet through pctx Code Mode writes TypeScript that computes the answer in a
sandbox and returns just the number, exactly, every time.

## The result (Goose on claude-haiku-4-5)

| Setup | Accuracy | Pass | $/run | Turns |
|---|---|---|---|---|
| Code Mode (pctx) | 100% | 4/4 | ~$0.07 | ~8 |
| Naive tool-calling | 0% | 0/4 | ~$0.03 | ~5 |

Asked the same question on different runs, the naive agent returned Maritime net
revenue as 2.70M, 2.85M, 3.05M, 2.96M (true: 31.14M), and flipped the top segment
from Aviation to Energy. Code Mode returned the exact same correct number every
run.

This is a right-vs-wrong and reliability story, not a cost story. Per-run cost is
comparable; the naive agent is sometimes cheaper because it bails early and
guesses.

## Prerequisites

- Docker, via colima (`brew install colima docker && colima start`), OrbStack, or
  Docker Desktop. colima users: the scripts auto-point `DOCKER_HOST` at the colima
  socket.
- uv: https://astral.sh/uv
- The avp CLI: `uv tool install avp-cli`
- gh (GitHub CLI), used to fetch the pctx binary.
- A Claude API key in `ANTHROPIC_API_KEY`.

## Run it

```bash
./setup.sh                              # one-time: agent, workbook, pctx image, env
ANTHROPIC_API_KEY=sk-ant-... ./run.sh   # the head-to-head board
```

`./run.sh --max-items 1` runs a single question (cheap smoke test).
`avp eval view` opens the most recent run on agentvoyagerproject.com.

## What's in here

- `make_nuke.py` — generates the messy workbook (`nuke.xlsx`) + `ground_truth.json` from a fixed seed.
- `verify_nuke.py` — proves the exact answers are recoverable from the sheet (so the eval is fair).
- `sheets_mcp.py` — an Arcade-style (arcade-mcp-server) sheets MCP over the workbook: `list_sheets`, `get_values`.
- `pctx.json` — registers the sheets MCP as a pctx upstream, exposing Code Mode.
- `Dockerfile.codemode` — the sandbox image: python sheets deps + the pctx binary (Deno is embedded in pctx).
- `nuke-baseline.commission.json` — goose → sheets MCP directly (naive).
- `nuke-codemode.commission.json` — goose → pctx → sheets MCP (Code Mode).
- `nuke.eval.json` — the four questions, expected answers, and scorer.

## Make your own demo

The pattern is "same agent, same questions, two tool paths." To make it yours:

- New data or questions: edit `make_nuke.py` (or drop in your own `nuke.xlsx`) and
  update the expected answers in `nuke.eval.json`, then re-run `./setup.sh`.
- A real Arcade tool instead of the local sheets MCP: point `pctx.json` at an
  Arcade MCP (HTTP url + auth) and point the baseline commission's `mcp_servers`
  at the same server. The naive-vs-Code-Mode comparison stays identical.
- A stronger model: change `model` in the two commission files, e.g.
  `anthropic/claude-opus-4-6`, for an "even the strongest model fails naive" run.

## Notes / gotchas

- colima doesn't use Docker's default socket; the scripts export
  `DOCKER_HOST=unix://$HOME/.colima/default/docker.sock` when the default isn't up.
- avp forwards `GOOSE_*` env vars into the sandbox; `run.sh` clears
  `GOOSE_PROVIDER` / `GOOSE_MODEL` so the commission's model wins.
- Every run executes in an isolated sandbox with default-deny networking.
