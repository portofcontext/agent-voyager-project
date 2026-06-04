# Coding katas: claude-code vs goose

Four "write code, run it, report the number" tasks, head-to-head on both
agents in fresh sandboxes, scored by exact match. The last kata
(`hamming-10000`, answer ≈ 2.9×10^17) is the hard one: brute-force scanning
can never reach it and sloppy dedup gives the wrong index, so it separates
agents that pick the right algorithm from ones that don't.

### Run this example

Docker running, agents installed, ≈ $0.50 on Haiku (8 runs):

```bash
export ANTHROPIC_API_KEY=sk-ant-...

uv run avp commission create coding-solver \
  --model claude-haiku-4-5 \
  --prompt "$(printf 'Solve this task by writing and running code.\n\nTask: {input}\n\nWork in your workspace: write a small Python script, execute it, and verify the result. Then reply with ONLY the final numeric answer — no prose, no code, no formatting.')"

uv run avp eval run avp-cli/examples/coding/coding.eval.json
uv run avp eval view
```

### How it was made

- The commission: the `avp commission create` command above (lands in `~/.avp/commissions/coding-solver.json`).
- The eval: `coding.eval.json` in this directory, authored by hand — inline dataset, `exact-match` scorer, both agents, commission by id. An eval is a JSON file, not code.
