# Coding katas: claude-code vs goose

A minimal coding eval: three small "write code, run it, report the answer"
tasks, run head-to-head on both in-tree agents and scored by exact match.
Each run happens in a fresh sandbox (the default `python:3.12-slim` world),
where the agent writes a script in its workspace, executes it, and replies
with the number; the trajectory records every tool call either agent made.

## How this was created

Two artifacts, both small. The **commission** (the agent-config under test)
was created with the CLI; it lands in your library at
`~/.avp/commissions/coding-solver.json`:

```bash
uv run avp commission create coding-solver \
  --model claude-haiku-4-5 \
  --prompt "$(printf 'Solve this task by writing and running code.\n\nTask: {input}\n\nWork in your workspace: write a small Python script, execute it, and verify the result. Then reply with ONLY the final numeric answer — no prose, no code, no formatting.')" \
  --tag example:coding
```

The **eval config** (`coding.eval.json`, in this directory) was authored by
hand — an eval is a JSON file, not code: the inline dataset (three katas with
expected answers), the `exact-match` scorer, the two agents, and the
commission referenced by id. No environment file is needed; the default
sandbox world already has Python.

### Run this example

Needs Docker running, both agents installed (`avp agent install goose` /
`claude-code`), and an Anthropic key. ~6 Haiku runs, ≈ $0.25.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GOOSE_PROVIDER=anthropic

uv run avp commission create coding-solver \
  --model claude-haiku-4-5 \
  --prompt "$(printf 'Solve this task by writing and running code.\n\nTask: {input}\n\nWork in your workspace: write a small Python script, execute it, and verify the result. Then reply with ONLY the final numeric answer — no prose, no code, no formatting.')" \
  --tag example:coding

uv run avp eval run avp-cli/examples/coding/coding.eval.json   # board per agent + head-to-head
uv run avp eval view                                           # open it on agentvoyagerproject.com
```
