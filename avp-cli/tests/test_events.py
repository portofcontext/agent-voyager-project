"""Following a Trajectory while the agent writes it."""

import json
from pathlib import Path

import pytest

from avp_cli import console
from avp_cli.runs import events


def event(type: str, data: dict, time: str = "2026-01-01T00:00:00Z") -> bytes:
    line = {
        "avp_version": "0.1",
        "id": type,
        "time": time,
        "run_id": "r",
        "type": type,
        "data": data,
    }
    return json.dumps(line).encode()


SHOWN = "error_occurred - invalid_commission: went wrong - 0.0s\n"
ERROR = event("error_occurred", {"error_code": "invalid_commission", "error_message": "went wrong"})


def test_each_line_prints_once_after_its_newline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trajectory = tmp_path / "trajectory.ndjson"
    follower = events.Follower(trajectory)
    follower.poll()
    assert capsys.readouterr().err == ""

    trajectory.write_bytes(ERROR + b"\n" + ERROR[:20])
    follower.poll()
    assert capsys.readouterr().err == SHOWN

    with trajectory.open("ab") as file:
        file.write(ERROR[20:] + b"\n")
    follower.poll()
    follower.poll()
    assert capsys.readouterr().err == SHOWN


def test_finish_prints_a_last_line_without_a_newline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trajectory = tmp_path / "trajectory.ndjson"
    trajectory.write_bytes(ERROR)
    follower = events.Follower(trajectory)
    follower.poll()
    assert capsys.readouterr().err == ""
    follower.finish()
    assert capsys.readouterr().err == SHOWN


def test_unknown_and_invalid_events(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trajectory = tmp_path / "trajectory.ndjson"
    unknown = event("future_event", {})
    invalid = event("error_occurred", {})
    trajectory.write_bytes(unknown + b"\n" + invalid + b"\n")
    events.Follower(trajectory).finish()
    assert capsys.readouterr().err.startswith("not a valid event: ")


def test_tool_calls_show_their_id_and_name_and_the_time_between(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trajectory = tmp_path / "trajectory.ndjson"
    invoked = event(
        "tool_invoked",
        {"tool_call_id": "call-1", "tool_name": "read", "tool_input": {}},
        "2026-01-01T00:00:00Z",
    )
    result = {"type": "tool_result", "tool_use_id": "call-1", "content": [], "is_error": True}
    returned = event(
        "tool_returned",
        {"tool_call_id": "call-1", "tool_name": "read", "duration_ms": 2500, "tool_result": result},
        "2026-01-01T00:00:02.5Z",
    )
    trajectory.write_bytes(invoked + b"\n" + returned + b"\n")
    events.Follower(trajectory).finish()
    assert capsys.readouterr().err.splitlines() == [
        "tool_invoked - call-1 read - 0.0s",
        "tool_returned - call-1 read, an error - 2.5s",
    ]


def test_verbose_shows_the_type_and_the_whole_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trajectory = tmp_path / "trajectory.ndjson"
    trajectory.write_bytes(ERROR + b"\n" + event("future_event", {"x": 1}) + b"\n")
    console.set_verbose(True)
    events.Follower(trajectory).finish()
    printed = capsys.readouterr().err
    assert printed.startswith("error_occurred\n{\n")
    assert '"error_message": "went wrong"' in printed
    assert "future_event\n{\n" in printed
    assert " - 0.0s" not in printed
