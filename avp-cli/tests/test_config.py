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
    kw.setdefault("model", "anthropic/claude-haiku-4-5-20251001")
    library.save(cid, Commission(schema_version="0.1", run_id=cid, **kw), commissions_dir=d)


@pytest.fixture
def lib(tmp_path):
    """A throwaway library with one 'baseline' wire Commission."""
    d = tmp_path / "commissions"
    _save(d, "baseline", prompt="{input}", model="x/m")
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


def test_commissions_map_binds_each_id_to_its_agent(tmp_path) -> None:
    # The `{agent_name: [ids]}` form binds by descriptor.agent_name (the one
    # public agent identity). Known agents' keys also imply `agents` locators
    # (identity → registry alias), so no separate "agents" key is needed.
    d = tmp_path / "commissions"
    _save(d, "for-goose", prompt="{input}")
    _save(d, "for-claude", prompt="{input}")
    cfg = _cfg(commissions={"goose": ["for-goose"], "avp-claude-agent-sdk": ["for-claude"]})
    ev = config.eval_from_dict(cfg, commissions_dir=d)
    assert {(s.id, s.agent) for s in ev.setups} == {
        ("for-goose", "goose"),
        ("for-claude", "avp-claude-agent-sdk"),
    }
    assert ev.agents == ["goose", "claude-code"]  # locators: registry aliases


def test_commissions_map_unknown_key_needs_explicit_agents(tmp_path) -> None:
    # A third-party agent's descriptor.agent_name has no registry locator, so
    # omitting "agents" is an error pointing at the fix...
    d = tmp_path / "commissions"
    _save(d, "mine", prompt="{input}")
    cfg = _cfg(commissions={"my-agent": ["mine"]})
    with pytest.raises(config.EvalConfigError, match='"agents" entry locating it'):
        config.eval_from_dict(cfg, commissions_dir=d)
    # ...and an explicit locator (their manifest path) makes the same map fine:
    # binding still keys on the identity, the locator just finds the agent.
    cfg["agents"] = ["./my-agent/avp-conformance.json"]
    ev = config.eval_from_dict(cfg, commissions_dir=d)
    assert ev.agents == ["./my-agent/avp-conformance.json"]
    assert {(s.id, s.agent) for s in ev.setups} == {("mine", "my-agent")}


def test_commissions_map_rejects_non_list_value(tmp_path) -> None:
    # The typed gate (EvalConfig) catches the shape with a field path.
    d = tmp_path / "commissions"
    _save(d, "baseline", prompt="{input}")
    with pytest.raises(config.EvalConfigError, match="not a valid eval config"):
        config.eval_from_dict(_cfg(commissions={"goose": "baseline"}), commissions_dir=d)


def test_prompt_without_input_slot_is_rejected_at_load(tmp_path) -> None:
    # EVAL-FORMAT.md §3: a prompt with no {input} would run byte-identical for
    # every case (the old behavior silently dropped the case input).
    d = tmp_path / "commissions"
    _save(d, "fixed", prompt="always the same task")
    with pytest.raises(config.EvalConfigError, match=r"without an \{input\} slot"):
        config.eval_from_dict(_cfg(commissions=["fixed"]), commissions_dir=d)
    # No prompt at all is the explicit opt-out: the case text IS the prompt.
    _save(d, "passthrough")
    ev = config.eval_from_dict(_cfg(commissions=["passthrough"]), commissions_dir=d)
    assert ev.setups[0].render_prompt(ev.dataset.items[0]) == "hi"


def test_unknown_top_level_key_is_rejected(lib) -> None:
    # The typed gate: unknown keys are typos, not extensions.
    with pytest.raises(config.EvalConfigError, match="commisions"):
        config.eval_from_dict(_cfg(commisions=["baseline"], commissions=None), commissions_dir=lib)


def test_eval_version_accepted_and_pinned(lib) -> None:
    assert config.eval_from_dict(_cfg(eval_version="0.1"), commissions_dir=lib)
    with pytest.raises(config.EvalConfigError, match="eval_version"):
        config.eval_from_dict(_cfg(eval_version="9.9"), commissions_dir=lib)


def test_missing_required_key_errors() -> None:
    with pytest.raises(config.EvalConfigError, match="commissions"):
        config.eval_from_dict({"dataset": _DATASET, "scorer": {"name": "exact-match"}})


def test_unknown_commission_id_errors(tmp_path) -> None:
    empty = tmp_path / "commissions"
    with pytest.raises(config.EvalConfigError, match="ghost"):
        config.eval_from_dict(_cfg(commissions=["ghost"]), commissions_dir=empty)


def test_inline_commission_is_rejected(lib) -> None:
    bad = _cfg(commissions=[{"schema_version": "0.1", "run_id": "x"}])
    with pytest.raises(config.EvalConfigError, match="not a valid eval config"):
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
    with pytest.raises(config.EvalConfigError, match="exact-match"):
        config.eval_from_dict(_cfg(scorer={"name": "nope"}), commissions_dir=lib)


def test_commission_carries_output_schema(tmp_path) -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    d = tmp_path / "commissions"
    _save(d, "schema-one", prompt="{input}", model="x/m", output_schema=schema)
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
    result = catalog.scaffold(
        catalog.get("custom"), tmp_path, agents=["goose"], commissions_dir=lib
    )
    assert result.installed == ["baseline", "variant-a"]
    # the installed file is a pure wire Commission
    assert isinstance(library.load("baseline", commissions_dir=lib), Commission)
    ev = config.load_eval(result.eval_path, commissions_dir=lib)
    assert ev.agents == ["goose"]
    assert [s.id for s in ev.setups] == ["baseline", "variant-a"]


def test_scaffold_skips_existing_commission(tmp_path) -> None:
    lib = tmp_path / "commissions"
    _save(lib, "baseline", prompt="mine", model="x/m")
    result = catalog.scaffold(catalog.get("custom"), tmp_path, commissions_dir=lib)
    assert "baseline" in result.skipped  # left my version untouched
    assert library.load("baseline", commissions_dir=lib).prompt == "mine"


def test_scaffold_without_agents_omits_the_key(tmp_path) -> None:
    lib = tmp_path / "commissions"
    result = catalog.scaffold(catalog.get("custom"), tmp_path, commissions_dir=lib)
    assert "agents" not in json.loads(result.eval_path.read_text())


def test_scaffold_twice_creates_a_second_file(tmp_path) -> None:
    lib = tmp_path / "commissions"
    first = catalog.scaffold(catalog.get("custom"), tmp_path, commissions_dir=lib)
    second = catalog.scaffold(catalog.get("custom"), tmp_path, commissions_dir=lib)
    assert first.eval_path.name == "custom.eval.json"
    assert second.eval_path.name == "custom-2.eval.json"
    assert second.installed == []
    assert sorted(second.skipped) == ["baseline", "variant-a"]


@pytest.mark.parametrize("entry", catalog.ENTRIES, ids=lambda e: e.key)
def test_every_catalog_entry_is_well_formed(entry: catalog.CatalogEntry) -> None:
    doc = catalog.load(entry)
    assert "dataset" in doc["eval"] and "source" in doc["eval"]["dataset"]
    assert "scorer" in doc["eval"] and "name" in doc["eval"]["scorer"]
    assert doc["commissions"]
    # every commission value is a valid wire Commission
    for spec in doc["commissions"].values():
        assert isinstance(Commission.model_validate(spec), Commission)
