"""Load an eval from a JSON config file. The config IS the eval; no user code.

A coding agent (or a developer) edits a JSON file and drives the CLI; the CLI is
the engine. Scorers are built in and chosen by name; datasets are referenced, not
loaded by user code; `commissions` is a list of ids resolved from the portable
commission library (`avp_cli.library`, `~/.avp/commissions/<id>.json`). Each
commission carries its own model, so there is no eval-level default.

Schema (eval.json):

    {
      "name": "parsebench-table",
      "agents": ["claude-code", "goose"],   # optional; --agent overrides at run time
      "dataset": { "source": "inline" | "file" | "huggingface", ... },
      "scorer":  { "name": "structural-match" | "exact-match" | "structural-fidelity" | "llm-judge", ...params },
      "commissions": ["baseline", "terse", "few-shot"]   # ids in the library, run on every agent
    }

`commissions` may instead be a per-agent map binding each commission to one
agent. Keys are the agents' self-declared `descriptor.agent_name` (what
`avp agent describe` prints), the same identity that keys a Commission's
`enabled_builtin_*` / `agent_versions` maps; `agents` entries stay locators
(a registry name or a manifest path). When every key belongs to a known
registry agent the top-level `agents` can be omitted (the keys imply it);
a third-party agent's key needs its manifest path listed in `agents`:

    "commissions": { "goose": ["baseline-goose"], "avp-claude-agent-sdk": ["baseline-claude"] }

Dataset sources:
  inline:      { "source": "inline", "items": [ {"id","prompt","expected"} ] }
  file:        { "source": "file", "path": "rows.jsonl", "input": "{question}", "expected_field": "answer" }
  huggingface: { "source": "huggingface", "id": "llamaindex/ParseBench", "split": "table[:10]",
                 "input": "https://.../{pdf}", "expected_field": "html", "id_field": "id" }
                 (needs the `huggingface` extra)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from avp_cli import library
from avp_cli.eval import template
from avp_cli.eval.dataset import Dataset, Item
from avp_cli.eval.engine import Eval
from avp_cli.eval.format import EvalConfig
from avp_cli.eval.scoring import (
    ExactMatchScorer,
    FidelityScorer,
    LLMJudgeScorer,
    Scorer,
    StructuralMatchScorer,
)
from avp_cli.eval.setup import Setup


class EvalConfigError(Exception):
    """A config file is missing required fields or names something unknown."""


def load_eval(path: str | Path, *, commissions_dir: Path | None = None) -> Eval:
    """Parse an eval JSON config into the internal Eval object."""
    p = Path(path)
    try:
        cfg = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalConfigError(f"could not read eval config {p}: {exc}") from exc
    if not isinstance(cfg, dict):
        raise EvalConfigError("eval config must be a JSON object")
    return eval_from_dict(cfg, name_hint=p.stem, commissions_dir=commissions_dir)


def eval_from_dict(
    cfg: dict[str, Any], *, name_hint: str = "eval", commissions_dir: Path | None = None
) -> Eval:
    # The typed gate first (avp_cli.eval.format, the schema's source of truth):
    # unknown keys, wrong shapes, and bad scorer/dataset names die here with a
    # field path. The engine assembly below then reads the validated dict.
    try:
        EvalConfig.model_validate(cfg)
    except ValidationError as exc:
        raise EvalConfigError(f"not a valid eval config: {exc}") from exc
    name = cfg.get("name", name_hint)
    dataset = _build_dataset(cfg["dataset"], name=name)
    scorer = _build_scorer(cfg["scorer"])
    commissions = _resolve_commissions(cfg["commissions"], commissions_dir=commissions_dir)
    # The map form `{agent_name: [ids]}` keys by descriptor.agent_name (an
    # identity); "agents" entries are locators. When agents is omitted, map
    # keys imply it for known registry agents (identity → registry alias);
    # a key no registry agent owns needs an explicit locator in "agents".
    agents_spec = cfg.get("agents")
    if agents_spec is None and isinstance(cfg["commissions"], dict):
        agents_spec = [_locator_for(k) for k in cfg["commissions"]]
    return Eval(
        setups=commissions,
        dataset=dataset,
        scorer=scorer,
        agents=_build_agents(agents_spec),
    )


def _reject_alias_key(key: str) -> None:
    """A commissions-map key that is a registry ALIAS (not the agent's
    descriptor.agent_name) would bind to nothing at run time, silently. Catch
    it at load with the exact fix. Aliases that equal the descriptor name
    (goose) pass through; only divergent ones (claude-code) can mislead."""
    from avp_cli.agents import AGENT_SOURCES

    source = AGENT_SOURCES.get(key)
    if source is not None and source.descriptor_name and source.descriptor_name != key:
        raise EvalConfigError(
            f"commissions key {key!r} is the CLI's install alias, not the agent's "
            f"identity; key it by descriptor.agent_name: {source.descriptor_name!r}. "
            f'("agents" entries stay locators, so {key!r} is still valid there.)'
        )


def _locator_for(agent_name: str) -> str:
    """Map a commissions-map key (a `descriptor.agent_name`) to a resolvable
    locator. Known registry agents resolve by their alias; anything else has
    no implicit locator and needs an explicit "agents" entry (a manifest path)."""
    from avp_cli.agents import AGENT_SOURCES

    for alias, source in AGENT_SOURCES.items():
        if agent_name in (alias, source.descriptor_name):
            return alias
    raise EvalConfigError(
        f"commissions key {agent_name!r} is not a known agent's name; add an "
        f'"agents" entry locating it (a registry name or a path to its '
        f"avp-conformance.json). Keys are descriptor.agent_name (see "
        f"`avp agent describe`)."
    )


def _build_agents(spec: Any) -> list[str]:
    if spec is None:
        return []
    if not isinstance(spec, list) or not all(isinstance(a, str) for a in spec):
        raise EvalConfigError('"agents" must be a list of agent names or manifest paths')
    return spec


# ── scorer registry ────────────────────────────────────────────────────────

_SCORERS = ("exact-match", "structural-match", "structural-fidelity", "llm-judge")


def _build_scorer(spec: dict[str, Any]) -> Scorer:
    if not isinstance(spec, dict) or "name" not in spec:
        raise EvalConfigError('scorer must be an object with a "name"')
    name = spec["name"]
    if name == "exact-match":
        return ExactMatchScorer()
    if name == "structural-match":
        return StructuralMatchScorer(threshold=float(spec.get("threshold", 1.0)))
    if name == "structural-fidelity":
        try:
            import rapidfuzz  # noqa: F401
        except ImportError as exc:
            raise EvalConfigError(
                "scorer 'structural-fidelity' needs the parsebench extra: "
                "uv sync --extra parsebench"
            ) from exc
        return FidelityScorer(threshold=float(spec.get("threshold", 0.8)))
    if name == "llm-judge":
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:
            raise EvalConfigError(
                "scorer 'llm-judge' needs the llm-judge extra: uv sync --extra llm-judge"
            ) from exc
        kwargs: dict[str, Any] = {}
        if "model" in spec:
            kwargs["grader_model"] = spec["model"]
        if "template" in spec:
            # Strict context (EVAL-FORMAT.md §3): a custom grader template may
            # only reference the judge's variable set. Catch typos at load,
            # not on the first paid grading call.
            judge_vars = {"question": "", "response": "", "correct_answer": ""}
            unknown = [n for n in template.variables_in(spec["template"]) if n not in judge_vars]
            if unknown:
                raise EvalConfigError(
                    f"llm-judge template references unknown name(s) {', '.join(unknown)}; "
                    "available: correct_answer, question, response"
                )
            kwargs["template"] = spec["template"]
        return LLMJudgeScorer(**kwargs)
    raise EvalConfigError(f"unknown scorer {name!r}; choose from {', '.join(_SCORERS)}")


# ── dataset sources ──────────────────────────────────────────────────────────


def _build_dataset(spec: dict[str, Any], *, name: str) -> Dataset:
    if not isinstance(spec, dict) or "source" not in spec:
        raise EvalConfigError('dataset must be an object with a "source"')
    source = spec["source"]
    if source == "inline":
        items = [_item_from_row(r, idx=i) for i, r in enumerate(spec.get("items", []))]
    elif source == "file":
        items = _load_file(spec)
    elif source == "huggingface":
        items = _load_huggingface(spec)
    else:
        raise EvalConfigError(f"unknown dataset source {source!r}: inline | file | huggingface")
    if not items:
        raise EvalConfigError(f"dataset '{name}' produced no items")
    return Dataset(name=name, items=items)


def _item_from_row(row: dict[str, Any], *, idx: int) -> Item:
    return Item(
        id=str(row.get("id", idx)),
        prompt=row["prompt"],
        expected=row.get("expected"),
    )


def _mapped_item(row: dict[str, Any], spec: dict[str, Any], idx: int) -> Item:
    """Map a raw dataset row to an Item via the config's field mapping.

    The `input` template renders by the eval format's single substitution
    rule (EVAL-FORMAT.md §3), strict for this context: it's a field mapping,
    so a token naming no row field is a typo and fails loudly."""
    input_tmpl = spec.get("input")
    if input_tmpl is None:
        raise EvalConfigError(f'dataset source {spec["source"]!r} needs an "input" template')
    try:
        prompt = template.render(input_tmpl, row, strict=True)
    except template.TemplateError as exc:
        raise EvalConfigError(f'dataset "input" template: {exc}') from exc
    id_field = spec.get("id_field")
    iid = str(row[id_field]) if id_field and id_field in row else str(idx)
    expected_field = spec.get("expected_field")
    expected = row.get(expected_field) if expected_field else None
    expected = _reduce_expected(expected, spec, iid)
    return Item(id=iid, prompt=prompt, expected=expected)


def _reduce_expected(expected: Any, spec: dict[str, Any], iid: str) -> Any:
    """Apply the optional `expected_pattern` (regex extraction) and
    `expected_key` (dict wrap) reductions to a raw expected value. Lets a
    benchmark whose gold lives inside a longer field (e.g. GSM8K's `#### 18`)
    feed exact-match / structural-match without a preprocessing step."""
    pattern = spec.get("expected_pattern")
    if pattern is not None and expected is not None:
        m = re.search(pattern, str(expected))
        if m is None:
            raise EvalConfigError(
                f"expected_pattern {pattern!r} did not match the "
                f"{spec.get('expected_field')!r} value for row {iid!r}"
            )
        expected = _coerce_scalar(m.group(1) if m.groups() else m.group(0))
    key = spec.get("expected_key")
    if key is not None:
        expected = {key: expected}
    return expected


def _coerce_scalar(text: str) -> Any:
    """Best-effort numeric coercion so structural-match's number tolerance
    applies: '1,024' -> 1024, '3.5' -> 3.5, 'cat' -> 'cat'."""
    stripped = text.strip().replace(",", "")
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        return text.strip()


def _load_file(spec: dict[str, Any]) -> list[Item]:
    path = Path(spec["path"])
    if not path.is_file():
        raise EvalConfigError(f"dataset file not found: {path}")
    text = path.read_text()
    if path.suffix == ".jsonl":
        rows = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    else:
        rows = json.loads(text)
    # if no mapping given, rows are already {id,prompt,expected}
    if spec.get("input") is None:
        return [_item_from_row(r, idx=i) for i, r in enumerate(rows)]
    return [_mapped_item(r, spec, i) for i, r in enumerate(rows)]


def _load_huggingface(spec: dict[str, Any]) -> list[Item]:
    try:
        import datasets
    except ImportError as exc:
        raise EvalConfigError(
            "dataset source 'huggingface' needs the huggingface extra: uv sync --extra huggingface"
        ) from exc
    # `config` is the dataset's subset/config name (HF's second positional arg);
    # multi-config datasets like gsm8k ("main") require it. None loads the default.
    ds = datasets.load_dataset(spec["id"], spec.get("config"), split=spec["split"])
    return [_mapped_item(dict(row), spec, i) for i, row in enumerate(ds)]


# ── commissions (referenced by id from the library) ─────────────────────────────


def _load_setup(cid: Any, *, agent: str | None, commissions_dir: Path | None) -> Setup:
    if not isinstance(cid, str):
        raise EvalConfigError(
            "commissions are referenced by id now, not inlined; save this one to your "
            "library (a JSON file in ~/.avp/commissions/) and list its id here. "
            f"got: {cid!r}"
        )
    try:
        base = library.load(cid, commissions_dir=commissions_dir)
    except library.CommissionError as exc:
        raise EvalConfigError(str(exc)) from exc
    # A prompt without the {input} slot would run BYTE-IDENTICAL for every
    # dataset case (the case input silently dropped) and the board would score
    # nonsense. Fail at load with the fix. A commission with no prompt at all
    # is the explicit fixed-slot opt-out: the case input becomes the prompt.
    if base.prompt and "input" not in template.variables_in(base.prompt):
        raise EvalConfigError(
            f"commission {cid!r} has a prompt without an {{input}} slot, so every "
            "dataset case would run the identical prompt. Add {input} where the "
            "case text goes, or remove the prompt to pass the case through verbatim."
        )
    return Setup(id=cid, commission=base, agent=agent)


def _resolve_commissions(specs: Any, *, commissions_dir: Path | None) -> list[Setup]:
    """Resolve the eval's `commissions` against the library.

    Two forms: a flat list `[<id>, ...]` (every commission runs on every agent),
    or a per-agent map `{<agent>: [<id>, ...]}` (each commission is bound to its
    agent, so an eval can give each agent a commission tuned in that agent's own
    tool namespace).
    """
    if isinstance(specs, dict):
        if not specs:
            raise EvalConfigError('"commissions" map must not be empty')
        commissions: list[Setup] = []
        for agent_name, ids in specs.items():
            _reject_alias_key(agent_name)
            if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
                raise EvalConfigError(
                    f'"commissions"[{agent_name!r}] must be a non-empty list of commission ids'
                )
            for cid in ids:
                commissions.append(
                    _load_setup(cid, agent=agent_name, commissions_dir=commissions_dir)
                )
        return commissions
    if not isinstance(specs, list) or not specs:
        raise EvalConfigError(
            '"commissions" must be a non-empty list of commission ids, '
            "or a {agent: [ids]} map to bind commissions to agents"
        )
    return [_load_setup(spec, agent=None, commissions_dir=commissions_dir) for spec in specs]
