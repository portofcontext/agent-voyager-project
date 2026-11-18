"""What `avp run` prints from a finished run's Trajectory."""

import json

import pytest
from conftest import atif

from avp_cli import console
from avp_cli.runs.summary import show


def test_steps_calls_and_results_print_in_order(tmp_path, capsys):
    path = tmp_path / "trajectory.json"
    steps = [
        {"step_id": 1, "source": "user", "message": "Read it"},
        {
            "step_id": 2,
            "source": "agent",
            "message": "",
            "metrics": {"prompt_tokens": 10, "completion_tokens": 2},
            "tool_calls": [{"tool_call_id": "c", "function_name": "read", "arguments": {}}],
            "observation": {
                "results": [
                    {
                        "source_call_id": "c",
                        "content": "failed",
                        "extra": {"avp": {"is_error": True}},
                    }
                ]
            },
        },
    ]
    path.write_text(json.dumps(atif(steps=steps)))
    show(path)
    assert capsys.readouterr().err == (
        "sh-agent: response - 10 in, 2 out tokens\n"
        "tool call - read (c)\n"
        "tool result - c - error\n"
        "sh-agent: converged\n"
    )


def test_a_refusal_shows_its_error(tmp_path, capsys):
    path = tmp_path / "trajectory.json"
    path.write_text(json.dumps(atif(error=("invalid_commission", "went wrong"))))
    show(path)
    assert capsys.readouterr().err == "invalid_commission: went wrong\nsh-agent: error\n"


def test_no_trajectory_prints_nothing(tmp_path, capsys):
    show(tmp_path / "trajectory.json")
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("text", ["not json", "{}"])
def test_invalid_document(tmp_path, capsys, text):
    path = tmp_path / "trajectory.json"
    path.write_text(text)
    show(path)
    assert capsys.readouterr().err == "not a valid ATIF document\n"


def test_verbose_shows_whole_document(tmp_path, capsys):
    path = tmp_path / "trajectory.json"
    path.write_text(json.dumps(atif()))
    console.set_verbose(True)
    show(path)
    assert '"schema_version": "ATIF-v1.8"' in capsys.readouterr().err
