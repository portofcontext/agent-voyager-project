# Onboarding eval: which way of teaching an agent AVP actually works?

A coding agent has never heard of AVP (it postdates its training). You can hand
it AVP knowledge a dozen ways: a Skill, an `llms.txt`, a docs dump, an
`AGENTS.md`, an MCP server, or just "the `avp` CLI is installed, go explore." Which
one actually makes the agent *competent* at AVP, per dollar and per turn?

This eval answers that with numbers, and it's wired into CI so a release that
makes AVP harder to onboard onto shows up as a regression instead of a surprise.

It's AVP measuring itself: an AVP eval whose subject is "how well can we onboard
an agent to AVP."

## The design

**The onboarding strategy is the commission variant.** Every commission runs the
same model over the same dataset; the *only* thing that varies is how AVP
knowledge reaches the agent. That isolates onboarding efficacy.

| Commission (strategy) | How AVP knowledge is delivered | Commission field |
|---|---|---|
| `cold` | nothing (control; measures training-data baseline) | — |
| `skill` | the AVP `SKILL.md` as an inline skill | `skills` |
| `llms-txt` | an `llms.txt` (full, inlined) in the system prompt | `system_prompt` |
| `readme-docs` | curated spec/README excerpts in the system prompt | `system_prompt` |
| `agents-md` | an `AGENTS.md` in the system prompt | `system_prompt` |
| `cursor-rules` | a `.cursor/rules` ruleset in the system prompt | `system_prompt` |
| `mcp` | an AVP knowledge MCP server (search + read the docs) | `mcp_servers` |
| `explore-cli` | "the `avp` CLI is installed; run `avp --help` and explore" | `system_prompt` + shell |

The artifacts each strategy ships live under [`strategies/`](strategies/), authored
with the best-practice skills from [skills.sh](https://skills.sh) (the Anthropic
`mcp-builder` and `skill-creator`, and an `llms.txt` generator).

**The dataset is leak-free "can you operate AVP" questions**, graded
deterministically with the CLI's existing `structural-match` scorer (each item
expects `{"answer": "<value>"}`; no LLM judge, so the CI gate is stable). The
questions are about the avp CLI / eval / supervisor layer — the acronym, the
`structural-fidelity` scorer, the `llamaindex/ParseBench` dataset id, `avp eval
run`, `avp cm check`, the `exact-match` scorer — which is exactly where a good
onboarding artifact beats a wire-focused one.

**Why these and not wire trivia ("what's the `source` on every event?").** A
first run taught us a methodology lesson worth recording: a tool-enabled agent can
read its own `/avp/io/trajectory.ndjson` — its own emitted events carry
`source: avp://agent`, the event-type names, and the commission snapshot — so any
"recite a wire fact" question is **self-leakable** and a cold agent can pass it by
`cat`-ing its own logs. The dataset therefore avoids facts that appear in an
agent's own runtime artifacts, and the recall strategies run with **no built-in
tools** (`enabled_builtin_tools: []`): the answer is in their context, so tools add
nothing but the ability to flail or peek. skill/mcp/explore-cli keep tools because
their delivery mechanism needs them.

A future, richer task ("author a ParseBench commission") is best graded by having
the agent write the artifact to a file and validating it with the CLI's own `avp
cm check` post-run — which sidesteps the leak (the grader validates; the agent
isn't quizzed on its own snapshot).

## Run it

```bash
# 1. install the agent(s) under test
avp agent install goose

# 2. generate the commissions from the strategy artifacts, install into the library
#    (library id is the filename stem, so drop the `.commission` suffix on copy)
python build_commissions.py
for f in strategies/*/*.commission.json; do
  cp "$f" ~/.avp/commissions/"$(basename "$f" .commission.json).json"
done

# 3. run the board (set the key for whatever model the commissions target)
export ANTHROPIC_API_KEY=sk-ant-...
avp eval run onboarding.eval.json
```

The board ranks each onboarding strategy by accuracy, pass-rate, cost/run, and
turns/run. The interesting columns are accuracy (did the strategy make the agent
competent?) against cost+turns (how expensive was that competence?).

## CI regression gate

[`.github/workflows/eval-onboarding.yml`](../../../.github/workflows/eval-onboarding.yml)
runs this eval on release tags against a committed baseline board
([`baseline.json`](baseline.json)) and fails if any strategy's accuracy drops past
the threshold. That is the point: when a CLI or spec change quietly breaks an
onboarding path (a stale skill, a renamed command, a changed wire field), the
number moves and the release is blocked until the artifact is fixed.
