"""The portable commission library: each file is a raw wire Commission."""

from __future__ import annotations

import json

import pytest

from avp.commission import Commission
from avp_cli import library


def _c(**kw) -> Commission:
    return Commission(schema_version="0.1", run_id=kw.pop("run_id", "r"), **kw)


def test_save_load_round_trip(tmp_path) -> None:
    d = tmp_path / "commissions"
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    c = _c(
        run_id="terse",
        prompt="Return JSON: {input}",
        model="claude-haiku-4-5",
        enabled_builtin_tools=["read_file"],
        output_schema=schema,
    )
    path = library.save("terse", c, commissions_dir=d)
    assert path.name == "terse.json"
    loaded = library.load("terse", commissions_dir=d)
    assert loaded == c  # full wire Commission round-trips


def test_saved_file_is_a_pure_wire_commission(tmp_path) -> None:
    # No tool-specific fields on disk — it must be portable to the cloud as-is.
    d = tmp_path / "commissions"
    library.save("terse", _c(prompt="{input}", model="m"), commissions_dir=d)
    raw = json.loads((d / "terse.json").read_text())
    assert "id" not in raw and "description" not in raw and "prompt_template" not in raw
    assert raw["schema_version"] == "0.1"
    assert raw["prompt"] == "{input}"


def test_load_missing_id_errors(tmp_path) -> None:
    with pytest.raises(library.CommissionError, match="no commission 'ghost'"):
        library.load("ghost", commissions_dir=tmp_path / "commissions")


def test_delete_removes_a_commission(tmp_path) -> None:
    d = tmp_path / "commissions"
    library.save("terse", _c(prompt="{input}"), commissions_dir=d)
    assert library.exists("terse", commissions_dir=d)
    assert library.delete("terse", commissions_dir=d) is True
    assert not library.exists("terse", commissions_dir=d)
    assert library.delete("terse", commissions_dir=d) is False  # already gone


def test_load_rejects_a_non_commission_file(tmp_path) -> None:
    d = tmp_path / "commissions"
    d.mkdir(parents=True)
    (d / "bad.json").write_text('{"nope": true}')
    with pytest.raises(library.CommissionError, match="not a valid wire Commission"):
        library.load("bad", commissions_dir=d)


def test_save_wont_overwrite_unless_asked(tmp_path) -> None:
    d = tmp_path / "commissions"
    library.save("x", _c(prompt="first"), commissions_dir=d)
    with pytest.raises(FileExistsError):
        library.save("x", _c(prompt="second"), commissions_dir=d)
    library.save("x", _c(prompt="second"), overwrite=True, commissions_dir=d)
    assert library.load("x", commissions_dir=d).prompt == "second"


def test_list_is_sorted_by_id(tmp_path) -> None:
    d = tmp_path / "commissions"
    for cid in ("terse", "baseline", "few-shot"):
        library.save(cid, _c(prompt="{input}"), commissions_dir=d)
    assert [cid for cid, _ in library.list_commissions(commissions_dir=d)] == [
        "baseline",
        "few-shot",
        "terse",
    ]


def test_exists(tmp_path) -> None:
    d = tmp_path / "commissions"
    assert not library.exists("x", commissions_dir=d)
    library.save("x", _c(prompt="hi"), commissions_dir=d)
    assert library.exists("x", commissions_dir=d)
