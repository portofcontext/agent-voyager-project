"""The config-driven loader: an eval is JSON, no user code.

Pins the config -> internal Eval contract, the scorer registry, the inline
dataset source, commission-by-id resolution against the (wire-Commission)
library, and that every packaged catalog entry is well-formed.
"""

from __future__ import annotations

import json

import pytest

from avp.commission import Commission
from avp_cli import catalog, config, library
from avp_cli.eval.scoring import ExactMatchScorer, FidelityScorer, StructuralMatchScorer

_DATASET = {"source": "inline", "items": [{"id": "i1", "prompt": "hi", "expected": "ok"}]}


def _save(d, cid, **kw) -> None:
    library.save(cid, Commission(schema_version="0.1", run_id=cid, **kw), commissions_dir=d)


@pytest.fixture
def lib(tmp_path):
    """A throwaway library with one 'baseline' wire Commission."""
    d = tmp_path / "commissions"
    _save(d, "baseline", prompt="{input}", model="m")
    return d


def _cfg(**over) -> dict:
    base = {"dataset": _DATASET, "scorer": {"name": "exact-match"}, "commissions": ["baseline"]}
    base.update(over)
    return base


def test_eval_from_dict_resolves_commission_ids(lib) -> None:
    ev = config.eval_from_dict(_cfg(), name_hint="t", commissions_dir=lib)
    assert [s.id for s in ev.setups] == ["baseline"]
    assert [it.id for it in ev.dataset.items] == ["i1"]
    assert isinstance(ev.scorer, ExactMatchScorer)


def test_missing_required_key_errors() -> None:
    with pytest.raises(config.EvalConfigError, match="commissions"):
        config.eval_from_dict({"dataset": _DATASET, "scorer": {"name": "exact-match"}})


def test_unknown_commission_id_errors(tmp_path) -> None:
    empty = tmp_path / "commissions"
    with pytest.raises(config.EvalConfigError, match="ghost"):
        config.eval_from_dict(_cfg(commissions=["ghost"]), commissions_dir=empty)


def test_inline_commission_is_rejected(lib) -> None:
    bad = _cfg(commissions=[{"schema_version": "0.1", "run_id": "x"}])
    with pytest.raises(config.EvalConfigError, match="referenced by id"):
        config.eval_from_dict(bad, commissions_dir=lib)


@pytest.mark.parametrize(
    ("spec", "cls"),
    [
        ({"name": "exact-match"}, ExactMatchScorer),
        ({"name": "structural-match", "threshold": 0.5}, StructuralMatchScorer),
    ],
)
def test_scorer_registry(lib, spec: dict, cls: type) -> None:
    ev = config.eval_from_dict(_cfg(scorer=spec), commissions_dir=lib)
    assert isinstance(ev.scorer, cls)


def test_unknown_scorer_errors(lib) -> None:
    with pytest.raises(config.EvalConfigError, match="unknown scorer"):
        config.eval_from_dict(_cfg(scorer={"name": "nope"}), commissions_dir=lib)


def test_commission_carries_output_schema(tmp_path) -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    d = tmp_path / "commissions"
    _save(d, "schema-one", prompt="{input}", model="m", output_schema=schema)
    ev = config.eval_from_dict(_cfg(commissions=["schema-one"]), commissions_dir=d)
    c = ev.setups[0].to_commission(ev.dataset.items[0], run_id="r")
    assert c.output_schema == schema


def test_structural_fidelity_requires_extra_when_rapidfuzz_absent(lib) -> None:
    try:
        import rapidfuzz  # noqa: F401
    except ImportError:
        with pytest.raises(config.EvalConfigError, match="parsebench extra"):
            config.eval_from_dict(_cfg(scorer={"name": "structural-fidelity"}), commissions_dir=lib)
    else:
        ev = config.eval_from_dict(
            _cfg(scorer={"name": "structural-fidelity"}), commissions_dir=lib
        )
        assert isinstance(ev.scorer, FidelityScorer)


def test_agents_default_to_empty_then_cli_chooses(lib) -> None:
    assert config.eval_from_dict(_cfg(), commissions_dir=lib).agents == []


def test_agents_key_flows_through(lib) -> None:
    ev = config.eval_from_dict(_cfg(agents=["claude-code", "goose"]), commissions_dir=lib)
    assert ev.agents == ["claude-code", "goose"]


def test_bad_agents_type_errors(lib) -> None:
    with pytest.raises(config.EvalConfigError, match="agents"):
        config.eval_from_dict(_cfg(agents="claude-code"), commissions_dir=lib)


def test_scaffold_installs_wire_commissions_and_eval_reloads(tmp_path) -> None:
    # Seam: scaffold writes wire Commissions to the library + an eval in place;
    # load_eval reads the eval and resolves its commission ids from the library.
    lib = tmp_path / "commissions"
    result = catalog.scaffold(catalog.get("demo"), tmp_path, agents=["goose"], commissions_dir=lib)
    assert result.installed == ["baseline", "terse", "few-shot"]
    # the installed file is a pure wire Commission
    assert isinstance(library.load("baseline", commissions_dir=lib), Commission)
    ev = config.load_eval(result.eval_path, commissions_dir=lib)
    assert ev.agents == ["goose"]
    assert [s.id for s in ev.setups] == ["baseline", "terse", "few-shot"]


def test_scaffold_skips_existing_commission(tmp_path) -> None:
    lib = tmp_path / "commissions"
    _save(lib, "baseline", prompt="mine", model="m")
    result = catalog.scaffold(catalog.get("demo"), tmp_path, commissions_dir=lib)
    assert "baseline" in result.skipped  # left my version untouched
    assert library.load("baseline", commissions_dir=lib).prompt == "mine"


def test_scaffold_without_agents_omits_the_key(tmp_path) -> None:
    lib = tmp_path / "commissions"
    result = catalog.scaffold(catalog.get("demo"), tmp_path, commissions_dir=lib)
    assert "agents" not in json.loads(result.eval_path.read_text())


def test_scaffold_twice_creates_a_second_file(tmp_path) -> None:
    lib = tmp_path / "commissions"
    first = catalog.scaffold(catalog.get("demo"), tmp_path, commissions_dir=lib)
    second = catalog.scaffold(catalog.get("demo"), tmp_path, commissions_dir=lib)
    assert first.eval_path.name == "demo.eval.json"
    assert second.eval_path.name == "demo-2.eval.json"
    assert second.installed == []
    assert sorted(second.skipped) == ["baseline", "few-shot", "terse"]


@pytest.mark.parametrize("entry", catalog.ENTRIES, ids=lambda e: e.key)
def test_every_catalog_entry_is_well_formed(entry: catalog.CatalogEntry) -> None:
    doc = catalog.load(entry)
    assert "dataset" in doc["eval"] and "source" in doc["eval"]["dataset"]
    assert "scorer" in doc["eval"] and "name" in doc["eval"]["scorer"]
    assert doc["commissions"]
    # every commission value is a valid wire Commission
    for spec in doc["commissions"].values():
        assert isinstance(Commission.model_validate(spec), Commission)
