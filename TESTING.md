# Testing AEP — the seams principle

> **One-line takeaway:** every bug we shipped lived at a seam between two
> components. Unit tests target individual components and miss seam bugs by
> construction. Add at least one seam-crossing test for every feature.

This doc records the test strategy across the AEP repo. Read it before adding
a feature; reference it when reviewing a PR.

---

## What "seam" means here

A **seam** is the boundary where two components hand work to each other and
where each side has assumptions about the other:

- CLI ↔ runner — the CLI reads stdin, builds drivers, drives `AEPRunner`,
  streams events to stdout
- runner ↔ driver (across multiple turns) — the runner accumulates history;
  the driver translates history ↔ provider format on every turn
- translator ↔ SDK — the Claude Agent SDK emits cumulative usage state; the
  translator must derive deltas
- supervisor ↔ runner subprocess — Config goes in on stdin, NDJSON comes out
  on stdout, RPC replies go back on stdin
- runner ↔ workspace — verifier shell paths, tool paths, file IO all resolve
  against the runner's CWD; the supervisor provisions that CWD

Bugs cluster at seams because each component, tested in isolation, looks
correct. They fail when one component's assumption disagrees with another's.

## Bugs we shipped, and the seam they lived at

| Bug | Seam | Why isolated tests missed it |
|---|---|---|
| `_capture_writer` reassigning `list.append` (Python forbids) | CLI ↔ runner | CLI's `main()` was never executed. Driver tests targeted translation; conformance used the reference runner directly. |
| Missing assistant-turn-with-tool-calls in history | runner ↔ driver across two turns | Conformance used `ScriptedModel` (history-shape-agnostic). Driver tests were single-turn. The bug only manifests on turn 2. |
| Cost double-counting in `aep-claude-agent` | translator ↔ SDK with realistic state | Translator unit tests passed independent canned `usage` dicts. The real SDK reports cumulative-per-message; we never simulated cumulative state. |
| Workspace `cwd` not propagated to runner subprocess | supervisor ↔ runner ↔ verifier | No example was run end-to-end with an API key before shipping. The verifier's `git diff` ran in the supervisor's CWD, not the workspace. |

The pattern is structural: **all four components had passing unit tests
when these bugs shipped**. The fix in each case was not "fix the unit
tests" — it was "add a test that crosses the seam."

---

## The test layers

| Layer | Where it lives | Catches | Cost |
|---|---|---|---|
| **JSON Schema validation** | `spec/v0.1/aep.schema.json` + `conformance/v0.1/validate.py` | Wire-format shape | Free |
| **Conformance suite** | `conformance/v0.1/cases/*.json` driven via `aep-conformance` against the reference runner with `ScriptedModel` | Runner loop semantics — boundary, verifier triggers, source discipline, allowed_tools, RPC lifecycle, custom-event passthrough | Free |
| **Component unit tests** | Each package's `tests/test_*.py` | Single-component behavior — driver translation, translator emission, observability summarization | Free |
| **Seam tests** (CLI smoke, multi-turn, cumulative-usage) | `tests/test_cli_smoke.py`, `tests/test_multi_turn.py`, `tests/test_translator.py::test_cumulative_*` | The bugs in the table above | Free |
| **Real-LLM smoke** | `tests/test_real_llm.py` (gated on `-m real_llm` and `ANTHROPIC_API_KEY`) | End-to-end correctness against actual model responses (cost, token math, cache, real tool dispatch) | ~$0.001 per test |
| **Examples as smoke** | `python/supervisors/simple-supervisor-example/examples/` | Exercising the full Config → runner → trajectory → summary flow on real LLMs in a narrative form | ~$0.01 per run |

Each layer catches what the layers above it miss. Skip a layer and you ship
its blind spots.

---

## When you add a feature

Add a test in **at least one** of these layers, and prefer the lowest cost:

1. **Wire-level rule (a MUST in SPEC.md)** → add a conformance case. These are
   cheap, fast, and provable with the existing harness. See
   `conformance/v0.1/cases/` for the format. Match a JSON pattern against
   the trajectory; assert ordering or forbidden events.

2. **New behavior in a single component** → unit test in that component's
   `tests/`. Mock the components on the other side of the seam.

3. **New behavior that depends on cross-component state** (history shape,
   cumulative usage, CLI lifecycle, subprocess cwd) → **seam test**. This is
   the layer that's easy to skip and where bugs hide. If your feature touches
   any of:
   - The CLI startup path
   - Runner state across turns
   - SDK / API client interaction
   - Subprocess invocation
   then you almost certainly need a seam test.

4. **Real-model behavior unique to a provider** → real-LLM smoke. Gate it on
   the marker so CI doesn't burn API credits by default.

## Specific patterns that work

- **CLI smoke** (in-process): import the CLI's `main()`, monkeypatch
  `stdin`/`stdout` to `io.StringIO`, monkeypatch the driver constructor to
  inject a `_SequencedClient` that returns canned responses. Parse the
  stdout NDJSON. See `python/runners/aep-anthropic/tests/test_cli_smoke.py`.

- **Multi-turn driver**: `_SequencedClient` with multiple scripted responses,
  then drive the full `AEPRunner` end-to-end. Inspect
  `client.calls[1]["messages"]` to assert the conversation shape between
  turns. See `python/runners/aep-anthropic/tests/test_multi_turn.py`.

- **Cumulative state**: when integrating with an SDK that reports running
  totals (token usage, costs), simulate the cumulative pattern with at least
  two messages where the second's value is GREATER than the first's, and
  assert per-event values are deltas, not the cumulative. See
  `python/runners/aep-claude-agent/tests/test_translator.py::test_cumulative_*`.

- **Workspace-sensitive verifier**: when a verifier or tool uses a relative
  path, run the runner subprocess with `cwd=<workspace>` and write a verifier
  whose result depends on the CWD. The conformance harness doesn't currently
  exercise CWD; do this as an integration test in the supervisor package.

## What we deliberately don't test

- **HTTP transport** — spec'd in §5.2 but not implemented. Add a test layer
  when the implementation lands.
- **Performance / latency** — out of scope for v0.1.
- **Trajectory size limits** — handled by event truncation in tooling, not in
  the protocol.
- **Schema migrations** — there's only v0.1.

---

## Current coverage snapshot

As of this commit:

- 19 conformance cases pinning wire-level MUSTs
- 19 unit tests in `aep` (parse_event passthrough, conformance harness)
- 14 tests in `aep-anthropic` (5 driver, 5 CLI smoke, 4 multi-turn driver)
- 7 tests in `aep-claude-agent` (translator emission + cumulative-usage)
- 6 tests in `simple-supervisor-example`
- 4 deselected real-LLM smoke tests (gated on key)

Total: 65 tests + 19 conformance cases. Run them all with:

```bash
# Free tier
for p in python/aep python/runners/aep-anthropic \
         python/runners/aep-claude-agent \
         python/supervisors/simple-supervisor-example; do
  (cd $p && uv run pytest -q -m "not real_llm")
done
uv run aep-conformance --suite conformance/v0.1/cases

# Real-LLM tier (~$0.005)
export ANTHROPIC_API_KEY="$(cat ~/.anthropic-key)"
(cd python/runners/aep-anthropic && uv run pytest -m real_llm)
```
