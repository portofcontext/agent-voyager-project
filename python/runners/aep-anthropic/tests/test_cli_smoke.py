"""CLI smoke tests for aep-anthropic.

These tests pipe a Config through the actual `aep-anthropic` CLI entry point
and assert the NDJSON event stream that comes out. They run with a mocked
Anthropic client (no API key, no network), so they're cheap to run on every
CI invocation.

The class of bug they catch: anything broken at the SEAM between the CLI and
the runner — code that unit tests skip because they target the driver in
isolation. The original `_capture_writer` regression that reassigned
`list.append` (which fails at runtime) was exactly this kind of bug; it lived
in `cli.py:main` and was not exercised by any test before these.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

import pytest

from aep_anthropic import cli as cli_module

# ── Mock infrastructure ───────────────────────────────────────────────────────


class _SequencedClient:
    """Anthropic client that returns scripted responses in order."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("CLI requested more model turns than the test scripted")
        return self._responses.pop(0)


def _resp(
    *,
    text: str | None = None,
    tool_use: dict | None = None,
    stop_reason: str = "end_turn",
    input_tokens: int = 50,
    output_tokens: int = 10,
) -> SimpleNamespace:
    blocks: list[Any] = []
    if text:
        blocks.append(SimpleNamespace(type="text", text=text))
    if tool_use:
        blocks.append(SimpleNamespace(type="tool_use", **tool_use))
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason=stop_reason,
    )


def _drive_cli(
    monkeypatch: pytest.MonkeyPatch,
    *,
    config_dict: dict,
    client: _SequencedClient,
) -> tuple[int, list[dict]]:
    """Run cli.main() in-process with mocked stdin/stdout and a stub Anthropic client.

    Returns (exit_code, parsed_events).
    """
    # Patch the driver constructor used inside cli.main() so it doesn't try
    # to instantiate a real anthropic.Anthropic() (which needs an API key).
    real_driver_cls = cli_module.AnthropicModelDriver

    def make_driver(**kwargs: Any):
        kwargs["client"] = client
        return real_driver_cls(**kwargs)

    monkeypatch.setattr(cli_module, "AnthropicModelDriver", make_driver)

    stdin = io.StringIO(json.dumps(config_dict) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(cli_module.sys, "stdin", stdin)
    monkeypatch.setattr(cli_module.sys, "stdout", stdout)

    exit_code = cli_module.main([])

    events = []
    for line in stdout.getvalue().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return exit_code, events


# ── Smoke tests ───────────────────────────────────────────────────────────────


def test_cli_text_only_run_emits_full_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI startup + streaming hookup + single-turn run.

    This is the test that would have caught the `_capture_writer` reassignment
    of `list.append` — the CLI used to crash before emitting any event."""

    client = _SequencedClient(
        [_resp(text="hello and DONE", stop_reason="end_turn", input_tokens=40, output_tokens=8)]
    )
    config = {
        "schema_version": "0.1",
        "run_id": "cli-smoke-text",
        "model": "claude-sonnet-4-6",
        "prompt": "say something",
    }

    code, events = _drive_cli(monkeypatch, config_dict=config, client=client)
    assert code == 0

    types = [e["type"] for e in events]
    assert types[0] == "agent_started"
    assert "model_turn_started" in types
    assert "model_turn_ended" in types
    assert "text_emitted" in types
    assert "cost_recorded" in types
    assert types[-1] == "agent_stopped"
    assert events[-1]["reason"] == "converged"
    # Every event has source=runner (no supervisor messages in this run)
    assert all(e["source"] == "runner" for e in events)


def test_cli_streaming_writes_one_event_per_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI MUST write events as NDJSON: one JSON object per line.
    No pretty-printing, no batching. SPEC.md §5.1."""
    client = _SequencedClient(
        [_resp(text="ok", stop_reason="end_turn", input_tokens=10, output_tokens=2)]
    )
    config = {"schema_version": "0.1", "run_id": "cli-ndjson", "model": "claude-sonnet-4-6"}

    code, events = _drive_cli(monkeypatch, config_dict=config, client=client)
    assert code == 0
    assert len(events) >= 4, (
        f"expected at least agent_started/turn_started/turn_ended/agent_stopped, got {len(events)}"
    )
    for ev in events:
        assert isinstance(ev, dict)
        assert "type" in ev and "source" in ev and "run_id" in ev


def test_cli_tool_call_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: assistant calls a runner-built-in tool, runner dispatches,
    text completes the turn. Verifies CLI's tools_param wiring + ShellTools
    dispatch + the multi-turn history we just fixed."""
    client = _SequencedClient(
        [
            _resp(
                tool_use={"id": "tu1", "name": "bash", "input": {"command": "echo hi"}},
                stop_reason="tool_use",
                input_tokens=30,
                output_tokens=12,
            ),
            _resp(text="result was hi", stop_reason="end_turn", input_tokens=80, output_tokens=8),
        ]
    )
    config = {
        "schema_version": "0.1",
        "run_id": "cli-tool",
        "model": "claude-sonnet-4-6",
        "prompt": "run echo hi",
        "allowed_tools": ["bash"],
    }
    code, events = _drive_cli(monkeypatch, config_dict=config, client=client)
    assert code == 0

    types = [e["type"] for e in events]
    assert "tool_invoked" in types
    assert "tool_returned" in types
    assert types[-1] == "agent_stopped"
    assert events[-1]["reason"] == "converged"

    # The tool_returned must contain the bash output
    returned = next(e for e in events if e["type"] == "tool_returned")
    assert returned["call_id"] == "tu1"
    assert returned["tool"] == "bash"
    assert "hi" in returned["output"]


def test_cli_bad_schema_version_emits_error_occurred_then_agent_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPEC.md §14: a Config with an unsupported schema_version MUST yield
    error_occurred (code='unknown') followed by agent_stopped (reason='error').
    The CLI must not crash silently — that violates the spec.

    Pre-fix the CLI did `Config.model_validate(...)` and let Pydantic
    ValidationError bubble up to the process boundary. The supervisor saw an
    abrupt EOF on stdout with no events. That's a spec violation."""
    bad_config = {"schema_version": "0.2", "run_id": "bad-version", "model": "x"}

    stdin = io.StringIO(json.dumps(bad_config) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(cli_module.sys, "stdin", stdin)
    monkeypatch.setattr(cli_module.sys, "stdout", stdout)

    code = cli_module.main([])
    assert code != 0  # exit non-zero on bad Config

    events = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert "error_occurred" in types
    assert types[-1] == "agent_stopped"
    assert events[-1]["reason"] == "error"
    err = next(e for e in events if e["type"] == "error_occurred")
    assert err["code"] == "unknown"
    assert err["run_id"] == "bad-version"


def test_cli_allowed_tools_filter_blocks_unlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    """If allowed_tools is set, the runner MUST surface tool_failed when the
    model calls something not in the list."""
    client = _SequencedClient(
        [
            _resp(
                tool_use={
                    "id": "tu1",
                    "name": "write_file",
                    "input": {"path": "/tmp/x", "content": "y"},
                },
                stop_reason="tool_use",
                input_tokens=30,
                output_tokens=12,
            ),
            _resp(text="blocked, ok", stop_reason="end_turn", input_tokens=40, output_tokens=5),
        ]
    )
    config = {
        "schema_version": "0.1",
        "run_id": "cli-allow",
        "model": "claude-sonnet-4-6",
        "allowed_tools": ["read_file"],  # write_file NOT in list
    }
    code, events = _drive_cli(monkeypatch, config_dict=config, client=client)
    assert code == 0

    types = [e["type"] for e in events]
    assert "tool_failed" in types, "calling a tool not in allowed_tools must emit tool_failed"
    failed = next(e for e in events if e["type"] == "tool_failed")
    assert failed["tool"] == "write_file"
    assert "allowed_tools" in failed["error"]
