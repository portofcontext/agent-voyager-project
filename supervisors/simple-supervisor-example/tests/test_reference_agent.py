"""CLI smoke tests for the reference avp-anthropic agent at
`examples/_anthropic_reference_agent.py`.

These pin behavior the broader spec mandates: a valid Commission runs
end-to-end against a mocked Anthropic client, an invalid Commission
emits `error_occurred` + `agent_stopped(reason="error")`, and the
`describe` subcommand prints the agent's Descriptor as JSON. They run
without an API key because the Anthropic client is stubbed.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


def _import_reference_agent() -> ModuleType:
    """Load `_anthropic_reference_agent.py` as a module without polluting
    sys.path for other tests."""
    examples_dir = Path(__file__).resolve().parents[1] / "examples"
    src = examples_dir / "_anthropic_reference_agent.py"
    spec = importlib.util.spec_from_file_location("anthropic_reference_agent", str(src))
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("anthropic_reference_agent", mod)
    spec.loader.exec_module(mod)
    return mod


class _SequencedClient:
    """Stub Anthropic client returning scripted responses in order."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError(
                "reference agent requested more model turns than the test scripted"
            )
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


def _drive(
    monkeypatch: pytest.MonkeyPatch,
    *,
    config_dict: dict,
    client: _SequencedClient,
) -> tuple[int, list[dict]]:
    """Run reference_agent.main([]) in-process with stubbed stdin/stdout
    and Anthropic client. Returns (exit_code, parsed_events)."""
    mod = _import_reference_agent()
    real_driver_cls = mod.AnthropicModelDriver

    def make_driver(**kwargs: Any):
        kwargs["client"] = client
        return real_driver_cls(**kwargs)

    monkeypatch.setattr(mod, "AnthropicModelDriver", make_driver)

    stdin = io.StringIO(json.dumps(config_dict) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)

    exit_code = mod.main([])

    events = []
    for line in stdout.getvalue().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return exit_code, events


# ── Smoke tests ───────────────────────────────────────────────────────────────


def test_text_only_run_emits_full_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Startup + streaming + single-turn run. Trajectory opens with the
    run prelude (run_requested + agent_described) before agent_started
    per `spec/v0.1/trajectory.md` §2.1."""
    client = _SequencedClient(
        [_resp(text="hello and DONE", stop_reason="end_turn", input_tokens=40, output_tokens=8)]
    )
    config = {
        "schema_version": "0.1",
        "run_id": "ref-text",
        "model": "claude-sonnet-4-6",
        "prompt": "say something",
    }
    code, events = _drive(monkeypatch, config_dict=config, client=client)
    assert code == 0

    types = [e["type"] for e in events]
    assert types[0] == "avp.run_requested"
    assert types[1] == "avp.agent_described"
    assert types[2] == "avp.agent_started"
    assert "avp.assistant_message" in types
    assert types[-1] == "avp.agent_stopped"
    assert events[-1]["data"]["avp.reason"] == "converged"
    # The model's text rides inside assistant_message.avp.content as a TextBlock
    # (there is no separate text_emitted event in v0.1).
    am = next(e for e in events if e["type"] == "avp.assistant_message")
    text_blocks = [b for b in am["data"]["avp.content"] if b.get("type") == "text"]
    assert any("DONE" in b["text"] for b in text_blocks)


def test_ndjson_envelope_one_event_per_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """NDJSON: one JSON object per line. No pretty-printing, no batching.
    `spec/v0.1/README.md` §3.1."""
    client = _SequencedClient(
        [_resp(text="ok", stop_reason="end_turn", input_tokens=10, output_tokens=2)]
    )
    config = {"schema_version": "0.1", "run_id": "ref-ndjson", "model": "claude-sonnet-4-6"}
    code, events = _drive(monkeypatch, config_dict=config, client=client)
    assert code == 0
    assert len(events) >= 4
    for ev in events:
        assert isinstance(ev, dict)
        assert ev.get("specversion") == "1.0"
        assert "id" in ev and "source" in ev and "type" in ev
        assert "subject" in ev and "time" in ev and "data" in ev


def test_tool_call_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: model calls bash, agent dispatches via ShellTools,
    text completes the turn."""
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
        "run_id": "ref-tool",
        "model": "claude-sonnet-4-6",
        "prompt": "run echo hi",
        "enabled_builtin_tools": ["bash"],
    }
    code, events = _drive(monkeypatch, config_dict=config, client=client)
    assert code == 0

    types = [e["type"] for e in events]
    assert "avp.tool_invoked" in types
    assert "avp.tool_returned" in types
    assert types[-1] == "avp.agent_stopped"
    assert events[-1]["data"]["avp.reason"] == "converged"

    returned = next(e for e in events if e["type"] == "avp.tool_returned")
    assert returned["data"]["avp.tool.call_id"] == "tu1"
    assert returned["data"]["avp.tool.name"] == "bash"
    # ShellTools runs the real `echo hi`; the result content is a plain string.
    assert "hi" in returned["data"]["avp.tool_result"]["content"]


def test_bad_schema_version_emits_error_then_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`spec/v0.1/README.md` §7: a Commission with an unsupported
    schema_version MUST yield error_occurred (code='unknown') followed
    by agent_stopped (reason='error')."""
    bad = {"schema_version": "0.2", "run_id": "bad-version", "model": "x"}

    mod = _import_reference_agent()
    stdin = io.StringIO(json.dumps(bad) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)

    code = mod.main([])
    assert code != 0

    events = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert "avp.error_occurred" in types
    assert types[-1] == "avp.agent_stopped"
    assert events[-1]["data"]["avp.reason"] == "error"
    err = next(e for e in events if e["type"] == "avp.error_occurred")
    assert err["data"]["avp.error.code"] == "unknown"
    assert err["subject"] == "bad-version"


def test_describe_subcommand_prints_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`describe` prints the Descriptor as JSON to stdout. The
    on-the-wire `agent_described.data["avp.descriptor"]` payload MUST
    match `descriptor().model_dump(by_alias=True, exclude_none=True)`."""
    mod = _import_reference_agent()
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    code = mod.main(["describe"])
    assert code == 0
    printed = json.loads(stdout.getvalue())
    expected = mod.descriptor().model_dump(by_alias=True, exclude_none=True)
    assert printed == expected
    assert printed["agent_name"] == "anthropic-reference-agent"


def test_describe_matches_agent_described_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `agent_described` event carries the same Descriptor the
    `describe` subcommand prints. Pre-flight introspection MUST match
    on-wire trajectory for the same agent build."""
    client = _SequencedClient(
        [_resp(text="ok", stop_reason="end_turn", input_tokens=5, output_tokens=1)]
    )
    config = {
        "schema_version": "0.1",
        "run_id": "ref-descriptor-seam",
        "model": "claude-sonnet-4-6",
        "supervisor": {"name": "test-supervisor"},
    }
    _, events = _drive(monkeypatch, config_dict=config, client=client)

    described = next(e for e in events if e["type"] == "avp.agent_described")
    mod = _import_reference_agent()
    expected = mod.descriptor().model_dump(by_alias=True, exclude_none=True)
    assert described["data"]["avp.descriptor"] == expected
