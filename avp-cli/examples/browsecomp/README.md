# BrowseComp eval (Claude Code Agent SDK)

Runs the [BrowseComp](https://openai.com/index/browsecomp/) browsing benchmark
against the `claude-code` agent via `avp eval`, scored the way
[openai/simple-evals](https://github.com/openai/simple-evals/blob/main/browsecomp_eval.py)
does it: an LLM grader decides `correct: yes|no` and accuracy is the fraction
marked correct.

## Files

- `decrypt_browsecomp.py` — one-off: decrypts the canary-protected CSV to JSONL.
- `browsecomp.eval.json` — the eval config (`llm-judge` scorer, `claude-code` agent).
- `browsecomp-claude.commission.json` — the commission (BrowseComp response-format
  prompt; leaves all builtin tools on so the agent can `WebSearch`/`WebFetch`).

A second example, comparing web-search backends (Exa vs Linkup), lives in
[`search-compare/`](search-compare/).

## Setup

```bash
# 1. the eval's grader runs in-process and needs the anthropic SDK
uv sync --extra llm-judge

# 2. install the agent (self-contained; just needs the `claude` CLI on PATH)
avp agent install claude-code

# 3. install the commission into your library (~/.avp/commissions)
cp browsecomp-claude.commission.json ~/.avp/commissions/browsecomp-claude.json

# 4. decrypt the dataset (reads ~/Downloads/browse_comp_test_set.csv)
cd avp-cli/examples/browsecomp
uv run python decrypt_browsecomp.py            # -> ./browse_comp.jsonl (gitignored)
```

`--extra llm-judge` is the only extra the eval needs; it covers the grader.
The agent is a separate subprocess that `avp agent install` makes self-contained
(`--extra claude-agent` is only for running the agent from this repo's source
instead of an installed build).

## Run

Run from this directory (the dataset `path` is resolved against the CWD).
Both the agent runs and the grader calls are paid, so start with a tiny slice:

```bash
export ANTHROPIC_API_KEY=...
avp eval run browsecomp.eval.json --max-items 3
```

Scale `--max-items` up once a small run looks clean. The full set is 1266 items.
