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
      "scorer":  { "name": "structural-match" | "exact-match" | "structural-fidelity", ...params },
      "commissions": ["baseline", "terse", "few-shot"]   # ids in the library
    }

Dataset sources:
  inline:      { "source": "inline", "items": [ {"id","prompt","expected"} ] }
  file:        { "source": "file", "path": "rows.jsonl", "input": "{question}", "expected_field": "answer" }
  huggingface: { "source": "huggingface", "id": "llamaindex/ParseBench", "split": "table[:10]",
                 "input": "https://.../{pdf}", "expected_field": "html", "id_field": "id" }
                 (needs the `huggingface` extra)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from avp_cli import library
from avp_cli.eval.dataset import Dataset, Item
from avp_cli.eval.engine import Eval
from avp_cli.eval.scoring import (
    ExactMatchScorer,
    FidelityScorer,
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
    for key in ("dataset", "scorer", "commissions"):
        if key not in cfg:
            raise EvalConfigError(f"eval config is missing required key {key!r}")
    name = cfg.get("name", name_hint)
    dataset = _build_dataset(cfg["dataset"], name=name)
    scorer = _build_scorer(cfg["scorer"])
    commissions = _resolve_commissions(cfg["commissions"], commissions_dir=commissions_dir)
    return Eval(
        setups=commissions,
        dataset=dataset,
        scorer=scorer,
        agents=_build_agents(cfg.get("agents")),
    )


def _build_agents(spec: Any) -> list[str]:
    if spec is None:
        return []
    if not isinstance(spec, list) or not all(isinstance(a, str) for a in spec):
        raise EvalConfigError('"agents" must be a list of agent names or manifest paths')
    return spec


# ── scorer registry ────────────────────────────────────────────────────────

_SCORERS = ("exact-match", "structural-match", "structural-fidelity")


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
    """Map a raw dataset row to an Item via the config's field mapping."""
    input_tmpl = spec.get("input")
    if input_tmpl is None:
        raise EvalConfigError(f'dataset source {spec["source"]!r} needs an "input" template')
    try:
        prompt = input_tmpl.format_map(row)
    except KeyError as exc:
        raise EvalConfigError(f"input template references unknown field {exc}") from exc
    expected_field = spec.get("expected_field")
    expected = row.get(expected_field) if expected_field else None
    id_field = spec.get("id_field")
    iid = str(row[id_field]) if id_field and id_field in row else str(idx)
    return Item(id=iid, prompt=prompt, expected=expected)


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
    ds = datasets.load_dataset(spec["id"], split=spec["split"])
    return [_mapped_item(dict(row), spec, i) for i, row in enumerate(ds)]


# ── commissions (referenced by id from the library) ─────────────────────────────


def _resolve_commissions(specs: Any, *, commissions_dir: Path | None) -> list[Setup]:
    """Resolve the eval's `commissions: [<id>, ...]` against the library."""
    if not isinstance(specs, list) or not specs:
        raise EvalConfigError('"commissions" must be a non-empty list of commission ids')
    commissions: list[Setup] = []
    for spec in specs:
        if not isinstance(spec, str):
            raise EvalConfigError(
                "commissions are referenced by id now, not inlined; save this one to your "
                "library (a JSON file in ~/.avp/commissions/) and list its id here. "
                f"got: {spec!r}"
            )
        try:
            base = library.load(spec, commissions_dir=commissions_dir)
        except library.CommissionError as exc:
            raise EvalConfigError(str(exc)) from exc
        commissions.append(Setup(id=spec, commission=base))
    return commissions
