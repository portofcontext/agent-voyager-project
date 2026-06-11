# The AVP eval format, 0.1

**Status:** Draft. The eval format is a CLI-layer artifact, NOT an AVP wire spec; it versions independently (`eval_version`).
**Schema:** [`eval.schema.json`](./eval.schema.json), generated from `avp_cli.eval.format.EvalConfig` (the source of truth) by `make schemas`.

The key words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are to be interpreted as described in RFC 2119.

This document defines the rules an eval runner (this CLI, a cloud runner, a third-party implementation) MUST reproduce so that the same `<name>.eval.json` plus the same commission library produce the same runs everywhere. Field shapes live in the schema; this file carries only the semantics a schema can't express.

---

## 1. The artifact

An eval is one JSON object (authored as `<name>.eval.json`, in place, in the user's project) declaring: a `dataset` (the cases), a `scorer` (built in, chosen by name), and `commissions` (which agent configurations to compare). Commissions are NOT inlined; they are referenced by id from the portable commission library (`~/.avp/commissions/<id>.json`, each file a raw AVP wire `Commission`). The eval file plus the referenced commission files are, together, the complete portable definition of the experiment.

`eval_version` identifies this format revision (`"0.1"`; omitted means `"0.1"` during 0.1). Implementations MUST reject configs that fail [`eval.schema.json`](./eval.schema.json); unknown keys are errors, not extensions.

## 2. Commission references: identities and locators

Two distinct kinds of agent string appear in an eval, and they MUST NOT be conflated:

- An **identity** is an agent's self-declared `descriptor.agent_name` (what its `describe` reports). Identities key the per-agent forms: the eval's `commissions: {<agent_name>: [ids]}` map, and (inside a Commission) the `enabled_builtin_*` and `agent_versions` maps.
- A **locator** is how a runner finds an agent: a registry name (`claude-code`) or a path to its `avp-conformance.json` manifest. Locators appear in `agents` and on the command line (`--agent`).

Rules:

1. A runner MUST bind per-agent commissions by comparing map keys against each resolved agent's `descriptor.agent_name`, never against the locator used to find it.
2. A runner MUST reject a `commissions` map key that is a known locator alias differing from that agent's identity (e.g. `"claude-code"` where the identity is `"avp-claude-agent-sdk"`): such a key would bind to nothing, silently.
3. When `agents` is omitted and `commissions` is a map, a runner MAY infer locators for keys it can map to known agents; a key it cannot map MUST be an error instructing the author to add a locator to `agents`.

## 3. Templating

Every templated string in the eval format substitutes by ONE rule. There is no other template syntax anywhere in the format.

**Grammar.** A variable token is `{name}` where `name` matches `[A-Za-z_][A-Za-z0-9_]*`. Nothing else is syntax: no format specs (`{x:>10}`), no attribute or index access (`{a.b}`, `{a[0]}`), no `{{` escapes. Braces not forming a token (`{two words}`, `{x: 1}`) are plain text.

**Algorithm.** Given a template and a set of defined variables:

1. Replace every token whose name is a defined variable with that variable's value, in a single pass; replacement text MUST NOT be rescanned (a value containing `{input}` stays literal).
2. String values substitute verbatim. Non-string values substitute as their JSON encoding (so `true`, not a host language's `True`).
3. A token whose name is NOT a defined variable is plain text, left verbatim.

**Strictness.** Each context declares whether undefined tokens are *allowed*:

| Context | Variables | Undefined tokens |
|---|---|---|
| A commission's `prompt` | `input` (the dataset case's text) | Allowed, literal (prompts legitimately contain braces, e.g. JSON examples) |
| A dataset's `input` mapping (`file` / `huggingface` sources) | the row's fields | Error at load (it's a field mapping; a stray token is a typo) |
| The `llm-judge` scorer's `template` | `question`, `response`, `correct_answer` | Error |

**The `{input}` contract.** A commission referenced from an eval either carries a `prompt` containing at least one `{input}` token (the runner substitutes the case text into it), or carries no `prompt` at all (the case text becomes the prompt verbatim). A runner MUST reject, at load, a referenced commission whose prompt lacks `{input}`: it would run byte-identical for every case, silently scoring nothing. Substitution happens supervisor-side, before the run's Commission is built; an unfilled template MUST NOT reach an agent.

**No escapes.** A template cannot produce a literal occurrence of a defined variable's own token. This is accepted as a limitation; the rule's one-paragraph implementability is worth more.

Reference implementation: `avp_cli/eval/template.py` (`render`).

## 4. Run stamping

For each (commission, dataset case) cell, the runner builds the run's wire Commission from the library file. It MUST:

1. Substitute `{input}` per §3 to produce the run's `prompt`.
2. Assign a fresh `run_id` (the library file's `run_id` is a placeholder; the id is the filename).
3. Stamp `supervisor` with its own name and version.
4. Append `commission:<id>` to `tags` (preserving existing tags) so trajectories attribute back to the library commission.
5. Apply a CLI-level model override (`--model`) to `model` when given; otherwise leave the commission's `model`.
6. Change nothing else: the library file's remaining fields (allowlists, pins, `mcp_servers`, `skills`, `output_schema`, ...) pass through verbatim.

Reference implementation: `avp_cli/eval/setup.py` (`Setup.to_commission`).

## 5. Datasets and scorers

Shapes are in the schema. Semantics a runner must match:

- `inline` items are `{id?, prompt, expected?}`; a missing `id` is the item's zero-based index as a string.
- `file` rows (`.json` array or `.jsonl`) are used as-is when no `input` template is given (rows already shaped `{id, prompt, expected}`); with `input`, each row maps through §3 (strict), `expected_field` / `id_field` selecting those columns.
- `huggingface` requires `id`, `split`, and an `input` template (§3, strict).
- Scorers are referenced by name; their scoring behavior is defined by this repo's implementations (`avp_cli/eval/scoring.py`). A runner reimplementing them MUST match scores, not just names, for boards to be comparable.
