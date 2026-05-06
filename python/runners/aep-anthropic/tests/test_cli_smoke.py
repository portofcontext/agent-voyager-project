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
    assert types[0] == "aep.agent_started"
    assert "aep.model_turn_started" in types
    assert "aep.model_turn_ended" in types
    assert "aep.text_emitted" in types
    assert "aep.cost_recorded" in types
    assert types[-1] == "aep.agent_stopped"
    assert events[-1]["data"]["aep.reason"] == "converged"
    # Every event has source=aep://runner (no supervisor messages in this run)
    assert all(e["source"] == "aep://runner" for e in events)


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
        # CloudEvents 1.0 envelope: every event has specversion, id, source, type,
        # subject (run_id), time, data.
        assert ev.get("specversion") == "1.0"
        assert "id" in ev and "source" in ev and "type" in ev
        assert "subject" in ev  # run_id
        assert "time" in ev
        assert "data" in ev


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
    assert "aep.tool_invoked" in types
    assert "aep.tool_returned" in types
    assert types[-1] == "aep.agent_stopped"
    assert events[-1]["data"]["aep.reason"] == "converged"

    # The tool_returned must contain the bash output
    returned = next(e for e in events if e["type"] == "aep.tool_returned")
    assert returned["data"]["gen_ai.tool.call.id"] == "tu1"
    assert returned["data"]["gen_ai.tool.name"] == "bash"
    assert "hi" in returned["data"]["aep.tool.result.text"]


def test_cli_bad_schema_version_emits_error_occurred_then_agent_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPEC.md §14: a Config with an unsupported schema_version MUST yield
    error_occurred (code='unknown') followed by agent_stopped (reason='error').
    The CLI must not crash silently — that violates the spec."""
    bad_config = {"schema_version": "0.2", "run_id": "bad-version", "model": "x"}

    stdin = io.StringIO(json.dumps(bad_config) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(cli_module.sys, "stdin", stdin)
    monkeypatch.setattr(cli_module.sys, "stdout", stdout)

    code = cli_module.main([])
    assert code != 0  # exit non-zero on bad Config

    events = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert "aep.error_occurred" in types
    assert types[-1] == "aep.agent_stopped"
    assert events[-1]["data"]["aep.reason"] == "error"
    err = next(e for e in events if e["type"] == "aep.error_occurred")
    assert err["data"]["aep.error.code"] == "unknown"
    assert err["subject"] == "bad-version"


def test_cli_subagent_invocation_emits_full_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: parent agent's tool_use targets a declared subagent. The CLI
    routes through the subagent dispatch path (NOT tool_invoked / tool_returned),
    AnthropicSubagentDriver runs a sub-loop using the same mocked client, and
    the trajectory shows: agent_started → parent turn(s) → subagent_invoked →
    nested model_turn pair → subagent_returned → parent's converging turn →
    agent_stopped(converged). Frame span_id pairs across invoked/returned.

    Crosses CLI ↔ runner ↔ subagent_driver — the seam most likely to drift,
    since the subagent driver instantiates a fresh AnthropicModelDriver from
    `aep_anthropic.subagent` (not the same import path as cli.py)."""

    # Three responses: parent calls subagent → subagent's one turn → parent converges.
    client = _SequencedClient(
        [
            _resp(
                tool_use={
                    "id": "tu1",
                    "name": "researcher",
                    "input": {"prompt": "summarize the file system"},
                },
                stop_reason="tool_use",
                input_tokens=30,
                output_tokens=12,
            ),
            _resp(
                text="The file system has src/, tests/, and docs/.",
                stop_reason="end_turn",
                input_tokens=15,
                output_tokens=12,
            ),
            _resp(
                text="Got it — research complete.",
                stop_reason="end_turn",
                input_tokens=80,
                output_tokens=8,
            ),
        ]
    )

    config = {
        "schema_version": "0.1",
        "run_id": "cli-subagent",
        "model": "claude-sonnet-4-6",
        "prompt": "delegate to the researcher",
        "subagents": [
            {
                "name": "researcher",
                "description": "Looks up info and reports back briefly.",
                "system_prompt": "You are a precise research assistant.",
                "model": "claude-haiku-4-5-20251001",
                "boundary": {"max_steps": 3},
            }
        ],
    }

    # The subagent driver instantiates its own AnthropicModelDriver from
    # `aep_anthropic.subagent` — patch THAT import so the same mock client is
    # injected into the sub-loop too.
    from aep_anthropic import subagent as subagent_module

    real_subagent_driver_cls = subagent_module.AnthropicModelDriver

    def make_subagent_inner_driver(**kwargs: Any):
        kwargs["client"] = client
        return real_subagent_driver_cls(**kwargs)

    monkeypatch.setattr(subagent_module, "AnthropicModelDriver", make_subagent_inner_driver)

    code, events = _drive_cli(monkeypatch, config_dict=config, client=client)
    assert code == 0

    types = [e["type"] for e in events]
    assert "aep.subagent_invoked" in types
    assert "aep.subagent_returned" in types
    # No tool_invoked for the subagent — it routes through its own lifecycle.
    tool_invokes_for_researcher = [
        e
        for e in events
        if e["type"] == "aep.tool_invoked" and e["data"]["gen_ai.tool.name"] == "researcher"
    ]
    assert not tool_invokes_for_researcher, "subagent calls MUST NOT surface as tool_invoked"

    invoked = next(e for e in events if e["type"] == "aep.subagent_invoked")
    returned = next(e for e in events if e["type"] == "aep.subagent_returned")
    assert invoked["data"]["gen_ai.agent.name"] == "researcher"
    assert invoked["data"]["gen_ai.operation.name"] == "invoke_agent"
    assert invoked["data"]["aep.subagent.input"] == {"prompt": "summarize the file system"}
    # Frame span MUST pair across the two events.
    assert invoked["data"]["span_id"] == returned["data"]["span_id"]

    # The subagent driver emitted at least one nested model_turn pair under the frame.
    frame_id = invoked["data"]["span_id"]
    nested_turns_started = [
        e
        for e in events
        if e["type"] == "aep.model_turn_started" and e["data"]["parent_span_id"] == frame_id
    ]
    assert len(nested_turns_started) >= 1, "subagent's internal model_turn chains under frame"

    # The subagent's result text is what the parent saw and the run converged.
    assert "file system" in returned["data"]["aep.subagent.result.text"]
    assert returned["data"]["aep.subagent.reason"] == "converged"
    assert types[-1] == "aep.agent_stopped"
    assert events[-1]["data"]["aep.reason"] == "converged"

    # The agent_started event surfaces the subagent on the wire (model-facing surface).
    started = next(e for e in events if e["type"] == "aep.agent_started")
    sa_decls = started["data"].get("subagents") or []
    assert len(sa_decls) == 1 and sa_decls[0]["name"] == "researcher"


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
    assert "aep.tool_failed" in types, "calling a tool not in allowed_tools must emit tool_failed"
    failed = next(e for e in events if e["type"] == "aep.tool_failed")
    assert failed["data"]["gen_ai.tool.name"] == "write_file"
    assert "allowed_tools" in failed["data"]["aep.tool.error"]
