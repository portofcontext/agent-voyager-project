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

**The dataset is verifiable AVP tasks**, graded deterministically with the CLI's
existing scorers (no LLM judge, so the CI gate is stable and free of grader
noise). No bespoke scorer: this example does not grow the shared scorer registry.

- **Conceptual facts** (what spec backs the event envelope? how many event types?
  what is the `source` on every event?) → `exact-match`.
- **Read a trajectory** (given NDJSON: total cost? stop reason? which tool ran?) →
  `exact-match`.
- **Author a Commission** for a scenario → `structural-match`: `item.expected` is
  the set of fields the answer must get right (`model`, `schema_version`, the right
  MCP-server `id`/`type`, an enabled built-in), scored as the fraction correct.
- **Capstone: author the ParseBench setup** — the `model`, the PDF-vision MCP
  server entry, the `structural-fidelity` scorer name, and the
  `llamaindex/ParseBench` dataset source. This is the "blank brain → does something
  real with AVP" target, scored field-by-field with `structural-match` /
  `exact-match`. We grade the *authored* config, not an execution: running it needs
  the HF dataset, a model, and the MCP server live in the agent's sandbox, which is
  a separate paid smoke, not a per-release gate.

`structural-match` checks the answer carries the right fields; it does not run the
full `Commission` validator. The rigorous version is a **follow-up**: have the
agent write the artifact to a file in its workspace and grade by running the CLI's
own `avp cm check` on it after the run. That reuses an existing validator and only
needs the scoring path to see the post-run workspace (a generic capability), rather
than a one-off scorer.

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
