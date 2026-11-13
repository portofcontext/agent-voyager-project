"""Follow native ATIF snapshots, including results attached to existing steps."""

import json

import pytest
from conftest import atif

from avp_cli import console
from avp_cli.runs.events import Follower


def test_updates_print_once(tmp_path, capsys):
    path = tmp_path / "trajectory.json"
    follower = Follower(path)
    follower.poll()
    assert capsys.readouterr().err == ""
    doc = atif(complete=False)
    path.write_text(json.dumps(doc))
    follower.poll()
    step = {
        "step_id": 2,
        "source": "agent",
        "message": "",
        "tool_calls": [{"tool_call_id": "c", "function_name": "read", "arguments": {}}],
    }
    doc["steps"].append(step)
    path.write_text(json.dumps(doc))
    follower.poll()
    assert "tool call - read (c)" in capsys.readouterr().err
    step["observation"] = {
        "results": [
            {"source_call_id": "c", "content": "failed", "extra": {"avp": {"is_error": True}}}
        ]
    }
    path.write_text(json.dumps(doc))
    follower.poll()
    assert capsys.readouterr().err == "tool result - c - error\n"
    follower.poll()
    follower.finish()
    assert capsys.readouterr().err == ""


def test_preflight_error_replaces_initial_placeholder(tmp_path, capsys):
    path = tmp_path / "trajectory.json"
    path.write_text(
        json.dumps(
            atif(
                steps=[{"step_id": 1, "source": "system", "message": "Run initialized."}],
                complete=False,
            )
        )
    )
    follower = Follower(path)
    follower.poll()
    path.write_text(json.dumps(atif(error=("invalid_commission", "went wrong"))))
    follower.finish()
    printed = capsys.readouterr().err
    assert "invalid_commission: went wrong" in printed
    assert "sh-agent: error" in printed


@pytest.mark.parametrize("text", ["not json", "{}"])
def test_invalid_document(tmp_path, capsys, text):
    path = tmp_path / "trajectory.json"
    path.write_text(text)
    Follower(path).finish()
    assert capsys.readouterr().err == "not a valid ATIF document\n"


def test_verbose_shows_whole_document(tmp_path, capsys):
    path = tmp_path / "trajectory.json"
    path.write_text(json.dumps(atif()))
    console.set_verbose(True)
    Follower(path).finish()
    assert '"schema_version": "ATIF-v1.8"' in capsys.readouterr().err
