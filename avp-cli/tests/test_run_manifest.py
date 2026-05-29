"""The per-run input snapshot (`run.json`).

A run dir must be a self-contained, immutable record of what produced it — the
library is a mutable working set, so the snapshot has to copy commission bodies,
not reference them. These tests pin that: full bodies + verbatim eval config are
written, and a later edit to the library can't change a run's snapshot.
"""

from __future__ import annotations

import json

from avp.commission import Commission
from avp_cli import library, run_manifest
from avp_cli.eval.setup import Setup

_DATASET = {"source": "inline", "items": [{"id": "i1", "prompt": "hi", "expected": "ok"}]}


def _setup(cid: str, agent: str | None, **fields) -> Setup:
    return Setup(
        id=cid,
        commission=Commission(schema_version="0.1", run_id=cid, **fields),
        agent=agent,
    )


def test_write_snapshots_full_bodies_agent_binding_and_config(tmp_path) -> None:
    out = tmp_path / "run"
    cfg = tmp_path / "x.eval.json"
    cfg.write_text(
        json.dumps(
            {
                "name": "x",
                "dataset": _DATASET,
                "scorer": {"name": "exact-match"},
                "commissions": {"goose": ["g"], "claude-code": ["c"]},
            }
        )
    )
    setups = [
        _setup("g", "goose", prompt="render {input}", enabled_builtin_tools=["shell"], model="m"),
        _setup("c", "claude-code", prompt="fetch {input}", model="m2"),
    ]
    run_manifest.write(
        out,
        run_id="swift-harbor",
        setups=setups,
        eval_config_path=cfg,
        agents=["goose", "claude-code"],
        model_override="claude-haiku-4-5",
        max_items=3,
        threshold_override=0.8,
    )
    m = run_manifest.read(out)
    assert m is not None
    assert m["run_id"] == "swift-harbor"
    assert m["run"] == {
        "agents": ["goose", "claude-code"],
        "model_override": "claude-haiku-4-5",
        "max_items": 3,
        "threshold_override": 0.8,
    }
    # verbatim eval config is embedded
    assert m["eval_config"]["commissions"] == {"goose": ["g"], "claude-code": ["c"]}
    # full commission bodies + agent binding, not just ids
    assert m["commissions"]["g"]["agent"] == "goose"
    assert m["commissions"]["g"]["commission"]["prompt"] == "render {input}"
    assert m["commissions"]["g"]["commission"]["enabled_builtin_tools"] == ["shell"]
    assert m["commissions"]["c"]["agent"] == "claude-code"
    assert m["cli_version"]  # recorded, non-empty


def test_snapshot_is_independent_of_later_library_edits(tmp_path) -> None:
    # Seam: the library is mutable; a run's snapshot must be a frozen copy, so
    # overwriting the library commission after the run does NOT alter the manifest.
    lib = tmp_path / "commissions"
    out = tmp_path / "run"
    library.save(
        "baseline",
        Commission(schema_version="0.1", run_id="baseline", prompt="ORIGINAL"),
        commissions_dir=lib,
    )
    setup = Setup(
        id="baseline", commission=library.load("baseline", commissions_dir=lib), agent="goose"
    )
    run_manifest.write(
        out,
        run_id="r",
        setups=[setup],
        eval_config_path=None,
        agents=["goose"],
        model_override=None,
        max_items=None,
    )
    # mutate the library the way this whole session did
    library.save(
        "baseline",
        Commission(schema_version="0.1", run_id="baseline", prompt="REWRITTEN"),
        commissions_dir=lib,
        overwrite=True,
    )
    assert library.load("baseline", commissions_dir=lib).prompt == "REWRITTEN"
    # the run's snapshot still holds what actually ran
    m = run_manifest.read(out)
    assert m["commissions"]["baseline"]["commission"]["prompt"] == "ORIGINAL"


def test_read_missing_manifest_returns_none(tmp_path) -> None:
    assert run_manifest.read(tmp_path) is None  # older runs have no run.json


def test_eval_config_path_none_embeds_null_config(tmp_path) -> None:
    out = tmp_path / "run"
    run_manifest.write(
        out,
        run_id="r",
        setups=[_setup("g", None, prompt="x")],
        eval_config_path=None,
        agents=["goose"],
        model_override=None,
        max_items=None,
    )
    m = run_manifest.read(out)
    assert m["eval_config"] is None and m["eval_config_path"] is None
