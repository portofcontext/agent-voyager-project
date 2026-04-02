"""Smoke tests for anthropic-aep.

All tests that make real API calls are skipped when ANTHROPIC_API_KEY is not
set. They're also marked ``slow`` so CI can skip them with ``-m "not slow"``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
FAST_MODEL = "claude-haiku-4-5-20251001"
SKIP_NO_KEY = pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY not set")
SLOW = pytest.mark.slow

RUNNER_DIR = Path(__file__).parent.parent


# ── helpers ───────────────────────────────────────────────────────────────────


def _events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _types(stdout: str) -> list[str]:
    return [e["type"] for e in _events(stdout)]


def _run_subprocess(config: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "anthropic_aep"],
        input=json.dumps(config),
        capture_output=True,
        text=True,
        cwd=RUNNER_DIR,
        env={**os.environ},
    )


def _make_text_response(text: str = "Hello!") -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    response.usage = MagicMock(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return response


def _make_tool_use_response(tool_name: str, call_id: str, inputs: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = call_id
    block.name = tool_name
    block.input = inputs

    response = MagicMock()
    response.content = [block]
    response.stop_reason = "tool_use"
    response.usage = MagicMock(
        input_tokens=20,
        output_tokens=8,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return response


def _tool_def(name: str = "my_tool") -> dict:
    return {
        "name": name,
        "description": f"A test tool called {name}",
        "input_schema": {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        },
    }


class _MockStream:
    """Minimal async context-manager + async-iterable mock for messages.stream()."""

    def __init__(self, response: MagicMock, events: list | None = None):
        self._response = response
        self._events = events or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for e in self._events:
            yield e

    async def get_final_message(self):
        return self._response


def _make_server_tool_use_event(name: str) -> MagicMock:
    """Simulate a content_block_start event with a server_tool_use block."""
    cb = MagicMock()
    cb.type = "server_tool_use"
    cb.name = name
    event = MagicMock()
    event.type = "content_block_start"
    event.content_block = cb
    return event


# ── unit: imports ─────────────────────────────────────────────────────────────


def test_imports():
    from anthropic_aep import query, run_from_stdin, supervise  # noqa: F401


def test_no_tool_definition_class():
    """ToolDefinition must not be exported — use plain dicts instead."""
    import anthropic_aep

    assert not hasattr(anthropic_aep, "ToolDefinition")


# ── unit: cost calculation ────────────────────────────────────────────────────


def test_compute_cost_known_model():
    from anthropic_aep._query import _compute_cost

    # Sonnet: $3/M input, $15/M output
    cost = _compute_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert abs(cost - 18.0) < 0.01


def test_compute_cost_vendor_prefix_stripped():
    from anthropic_aep._query import _compute_cost

    cost_plain = _compute_cost("claude-sonnet-4-6", 100, 50)
    cost_vendor = _compute_cost("anthropic/claude-sonnet-4-6", 100, 50)
    assert abs(cost_plain - cost_vendor) < 1e-9


def test_compute_cost_unknown_model_uses_default():
    from anthropic_aep._query import _compute_cost

    cost = _compute_cost("some-future-model", 1000, 500)
    assert cost > 0


def test_compute_cost_cache_tokens_increase_cost():
    from anthropic_aep._query import _compute_cost

    base = _compute_cost("claude-sonnet-4-6", 1000, 500, 0, 0)
    extra = _compute_cost("claude-sonnet-4-6", 1000, 500, 1000, 500)
    assert extra > base


# ── unit: query() with mocked Anthropic client ───────────────────────────────


@pytest.mark.asyncio
async def test_query_emits_agent_start_stop(capsys):
    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(
            return_value=_MockStream(_make_text_response("Hi"))
        )

        async for _ in __import__("anthropic_aep").query(
            prompt="Say hi",
            model=FAST_MODEL,
            run_id="test-001",
        ):
            pass

    out = capsys.readouterr().out
    types = _types(out)
    assert types[0] == "agent_start"
    assert types[-1] == "agent_stop"
    assert _events(out)[0]["run_id"] == "test-001"
    assert _events(out)[0]["model"] == FAST_MODEL


@pytest.mark.asyncio
async def test_query_emits_text_output(capsys):
    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(
            return_value=_MockStream(_make_text_response("Hello world"))
        )

        async for _ in __import__("anthropic_aep").query(
            prompt="Say hello",
            model=FAST_MODEL,
            run_id="test-text",
        ):
            pass

    out = capsys.readouterr().out
    assert "text_output" in _types(out)
    text_event = next(e for e in _events(out) if e["type"] == "text_output")
    assert "Hello world" in text_event["text"]


@pytest.mark.asyncio
async def test_query_emits_model_turn_events(capsys):
    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(
            return_value=_MockStream(_make_text_response())
        )

        async for _ in __import__("anthropic_aep").query(
            prompt="Hi",
            model=FAST_MODEL,
            run_id="test-turn",
        ):
            pass

    types = _types(capsys.readouterr().out)
    assert "model_turn_start" in types
    assert "model_turn_end" in types
    assert "cost_update" in types


@pytest.mark.asyncio
async def test_query_calls_tool_and_emits_events(capsys):
    calls: list[dict] = []

    tool_response = _make_tool_use_response("my_tool", "call-abc", {"x": "hello"})
    end_response = _make_text_response("All done")

    responses = [tool_response, end_response]
    call_count = 0

    def _stream_factory(**_kwargs):
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return _MockStream(r)

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(side_effect=_stream_factory)

        async for _ in __import__("anthropic_aep").query(
            prompt="Use my_tool",
            model=FAST_MODEL,
            tools=[_tool_def("my_tool")],
            tool_handlers={"my_tool": lambda inp: calls.append(inp) or "done"},
            run_id="test-tool",
        ):
            pass

    assert calls == [{"x": "hello"}]

    out = capsys.readouterr().out
    types = _types(out)
    assert "tool_call" in types
    assert "tool_result" in types

    tc = next(e for e in _events(out) if e["type"] == "tool_call")
    assert tc["tool"] == "my_tool"
    assert tc["input"] == {"x": "hello"}

    tr = next(e for e in _events(out) if e["type"] == "tool_result")
    assert tr["tool"] == "my_tool"
    assert tr["output"] == "done"


@pytest.mark.asyncio
async def test_query_no_skill_execute_for_regular_tools(capsys):
    """skill_execute must NOT be emitted for user-defined tool calls.

    skill_execute is reserved for Anthropic Agent Skills (server_tool_use
    blocks). Regular tool_handlers only emit tool_call / tool_result.
    """
    tool_response = _make_tool_use_response("my_tool", "call-sk1", {})
    end_response = _make_text_response()

    responses = [tool_response, end_response]
    call_count = 0

    def _stream_factory(**_kwargs):
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return _MockStream(r)

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(side_effect=_stream_factory)

        async for _ in __import__("anthropic_aep").query(
            prompt="Use the tool",
            model=FAST_MODEL,
            tools=[_tool_def("my_tool")],
            tool_handlers={"my_tool": lambda _: "result"},
            run_id="test-no-skill-execute",
        ):
            pass

    out = capsys.readouterr().out
    assert "skill_execute" not in _types(out)
    assert "tool_call" in _types(out)
    assert "tool_result" in _types(out)


@pytest.mark.asyncio
async def test_query_no_skill_execute_without_handler(capsys):
    """tool_call emitted but no skill_execute when no handler is registered."""
    tool_response = _make_tool_use_response("unhandled_tool", "call-u1", {})
    end_response = _make_text_response()

    responses = [tool_response, end_response]
    call_count = 0

    def _stream_factory(**_kwargs):
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return _MockStream(r)

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(side_effect=_stream_factory)

        async for _ in __import__("anthropic_aep").query(
            prompt="Use unhandled_tool",
            model=FAST_MODEL,
            tools=[_tool_def("unhandled_tool")],
            # no tool_handlers
            run_id="test-no-skill",
        ):
            pass

    out = capsys.readouterr().out
    assert "skill_execute" not in _types(out)
    assert "tool_call" in _types(out)


@pytest.mark.asyncio
async def test_query_emits_skill_execute_for_server_tool_use(capsys):
    """skill_execute IS emitted when a server_tool_use block appears in stream.

    This is the real Anthropic Agent Skills code path: the model runs a
    skill inside a code_execution container and the stream contains a
    content_block_start event with type=server_tool_use.
    """
    skill_event = _make_server_tool_use_event("pptx")
    response = _make_text_response("Done")

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(
            return_value=_MockStream(response, events=[skill_event])
        )

        async for _ in __import__("anthropic_aep").query(
            prompt="Generate a presentation",
            model=FAST_MODEL,
            skills=[{"type": "anthropic", "skill_id": "pptx", "version": "latest"}],
            run_id="test-server-skill",
        ):
            pass

    out = capsys.readouterr().out
    types = _types(out)
    assert "skill_execute" in types
    se = next(e for e in _events(out) if e["type"] == "skill_execute")
    assert se["name"] == "pptx"


@pytest.mark.asyncio
async def test_query_emits_skill_read_when_skills_provided(capsys):
    """skill_read events emitted at startup for each Anthropic Agent Skill."""
    response = _make_text_response("Done")

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(return_value=_MockStream(response))

        async for _ in __import__("anthropic_aep").query(
            prompt="Do something",
            model=FAST_MODEL,
            skills=[
                {"type": "anthropic", "skill_id": "pptx", "version": "latest"},
                {"type": "anthropic", "skill_id": "xlsx", "version": "latest"},
            ],
            run_id="test-skill-read",
        ):
            pass

    out = capsys.readouterr().out
    skill_reads = [e for e in _events(out) if e["type"] == "skill_read"]
    names = [e["name"] for e in skill_reads]
    assert "pptx" in names
    assert "xlsx" in names


@pytest.mark.asyncio
async def test_query_skills_passes_container_to_api(capsys):
    """When skills provided, container and betas are forwarded to the SDK."""
    response = _make_text_response("Done")
    captured_kwargs: list[dict] = []

    def _stream_factory(**kwargs):
        captured_kwargs.append(kwargs)
        return _MockStream(response)

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(side_effect=_stream_factory)

        async for _ in __import__("anthropic_aep").query(
            prompt="Do something",
            model=FAST_MODEL,
            skills=[{"type": "anthropic", "skill_id": "pptx", "version": "latest"}],
            run_id="test-skill-kwargs",
        ):
            pass

    assert captured_kwargs, "stream was never called"
    kw = captured_kwargs[0]
    assert "container" in kw
    assert "betas" in kw
    assert "skills-2025-10-02" in kw["betas"]


@pytest.mark.asyncio
async def test_query_respects_max_steps(capsys):
    tool_response = _make_tool_use_response("loop_tool", "call-loop", {})

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(return_value=_MockStream(tool_response))
        # reset side_effect so it keeps returning the same response
        mock_client.messages.stream.side_effect = lambda **_: _MockStream(tool_response)

        async for _ in __import__("anthropic_aep").query(
            prompt="Loop forever",
            model=FAST_MODEL,
            tools=[_tool_def("loop_tool")],
            tool_handlers={"loop_tool": lambda _: "keep going"},
            max_steps=3,
            run_id="test-maxsteps",
        ):
            pass

    out = capsys.readouterr().out
    stop = next(e for e in _events(out) if e["type"] == "agent_stop")
    assert stop["reason"] == "turn_limit"
    assert stop["total_turns"] == 3


@pytest.mark.asyncio
async def test_query_token_limit_stop_reason(capsys):
    response = MagicMock()
    response.content = []
    response.stop_reason = "max_tokens"
    response.usage = MagicMock(
        input_tokens=100,
        output_tokens=4096,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(return_value=_MockStream(response))

        async for _ in __import__("anthropic_aep").query(
            prompt="Write a book",
            model=FAST_MODEL,
            run_id="test-tokenlimit",
        ):
            pass

    stop = next(
        e for e in _events(capsys.readouterr().out) if e["type"] == "agent_stop"
    )
    assert stop["reason"] == "token_limit"


@pytest.mark.asyncio
async def test_query_unknown_tool_returns_error_string(capsys):
    tool_response = _make_tool_use_response("ghost_tool", "call-gh", {"x": 1})
    end_response = _make_text_response()

    responses = [tool_response, end_response]
    call_count = 0

    def _stream_factory(**_kwargs):
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return _MockStream(r)

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(side_effect=_stream_factory)

        async for _ in __import__("anthropic_aep").query(
            prompt="Call ghost tool",
            model=FAST_MODEL,
            run_id="test-unknown",
        ):
            pass

    tr = next(e for e in _events(capsys.readouterr().out) if e["type"] == "tool_result")
    assert "Unknown tool" in tr["output"]


@pytest.mark.asyncio
async def test_query_handler_exception_captured(capsys):
    tool_response = _make_tool_use_response("boom_tool", "call-boom", {})
    end_response = _make_text_response()

    responses = [tool_response, end_response]
    call_count = 0

    def _stream_factory(**_kwargs):
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return _MockStream(r)

    def bad_handler(_: dict) -> str:
        raise ValueError("boom")

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(side_effect=_stream_factory)

        async for _ in __import__("anthropic_aep").query(
            prompt="Call boom_tool",
            model=FAST_MODEL,
            tools=[_tool_def("boom_tool")],
            tool_handlers={"boom_tool": bad_handler},
            run_id="test-handler-exc",
        ):
            pass

    out = capsys.readouterr().out
    tr = next(e for e in _events(out) if e["type"] == "tool_result")
    assert "Error" in tr["output"] and "boom" in tr["output"]
    stop = next(e for e in _events(out) if e["type"] == "agent_stop")
    assert stop["reason"] == "converged"


@pytest.mark.asyncio
async def test_query_yields_message_objects():
    response = _make_text_response("Hi")
    yielded = []

    with patch("anthropic_aep._query.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(return_value=_MockStream(response))

        async for msg in __import__("anthropic_aep").query(
            prompt="Hi",
            model=FAST_MODEL,
        ):
            yielded.append(msg)

    assert yielded == [response]


# ── unit: run_from_stdin error cases ─────────────────────────────────────────


def test_run_from_stdin_empty_stdin():
    result = subprocess.run(
        [sys.executable, "-m", "anthropic_aep"],
        input="",
        capture_output=True,
        text=True,
        cwd=RUNNER_DIR,
        env={**os.environ},
    )
    assert result.returncode == 1
    assert "empty stdin" in result.stderr


def test_run_from_stdin_invalid_json():
    result = subprocess.run(
        [sys.executable, "-m", "anthropic_aep"],
        input="not json",
        capture_output=True,
        text=True,
        cwd=RUNNER_DIR,
        env={**os.environ},
    )
    assert result.returncode == 1
    assert "invalid" in result.stderr.lower()


# ── integration: subprocess runner ───────────────────────────────────────────


@SKIP_NO_KEY
@SLOW
def test_run_from_stdin_minimal_emits_valid_stream():
    config = {
        "run_id": "anthropic-smoke-001",
        "prompt": "Say hello in one sentence. Use no tools.",
        "model": f"anthropic/{FAST_MODEL}",
    }
    result = _run_subprocess(config)
    assert result.returncode == 0, f"runner failed:\n{result.stderr}"
    types = _types(result.stdout)
    assert types[0] == "agent_start"
    assert types[-1] == "agent_stop"
    assert _events(result.stdout)[0]["run_id"] == "anthropic-smoke-001"


@SKIP_NO_KEY
@SLOW
def test_run_from_stdin_without_model_uses_default():
    config = {
        "run_id": "anthropic-smoke-no-model",
        "prompt": "Say hello in one sentence. Use no tools.",
    }
    result = _run_subprocess(config)
    assert result.returncode == 0, f"runner failed:\n{result.stderr}"
    events = _events(result.stdout)
    assert events[0]["type"] == "agent_start"
    assert events[-1]["type"] == "agent_stop"


@SKIP_NO_KEY
@SLOW
def test_run_from_stdin_with_boundary():
    config = {
        "run_id": "anthropic-smoke-boundary",
        "prompt": "Count from 1 to 100, one number per message.",
        "model": f"anthropic/{FAST_MODEL}",
        "boundary": {"max_steps": 2},
    }
    result = _run_subprocess(config)
    assert result.returncode == 0, f"runner failed:\n{result.stderr}"
    stop = next(e for e in _events(result.stdout) if e["type"] == "agent_stop")
    assert stop["reason"] in ("turn_limit", "converged")


@SKIP_NO_KEY
@SLOW
async def test_query_drop_in_emits_agent_start_stop(capsys):
    from anthropic_aep import query

    async for _ in query(
        prompt="Say hello in one sentence. Use no tools.",
        model=FAST_MODEL,
        run_id="anthropic-lib-001",
    ):
        pass

    out = capsys.readouterr().out
    types = _types(out)
    assert types[0] == "agent_start"
    assert types[-1] == "agent_stop"
    assert _events(out)[0]["run_id"] == "anthropic-lib-001"


@SKIP_NO_KEY
@SLOW
async def test_query_with_tool_emits_structured_output(capsys):
    """Real API call: model uses a tool and structured output is validated."""
    from anthropic_aep import query

    results: list[dict] = []

    tools = [
        {
            "name": "record_finding",
            "description": "Record a finding. Call this once with the sentiment and summary.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sentiment": {
                        "type": "string",
                        "enum": ["positive", "negative", "neutral"],
                    },
                    "summary": {"type": "string"},
                },
                "required": ["sentiment", "summary"],
            },
        }
    ]

    def handle_record(inp: dict) -> str:
        results.append(inp)
        return "Recorded."

    async for _ in query(
        prompt=(
            "Analyse this text and call record_finding exactly once: "
            "'The new product launch exceeded all expectations and customers love it.'"
        ),
        model=FAST_MODEL,
        tools=tools,
        tool_handlers={"record_finding": handle_record},
        run_id="anthropic-tool-001",
    ):
        pass

    out = capsys.readouterr().out
    types = _types(out)

    # skill_execute must NOT appear — this is a regular tool, not an Agent Skill
    assert "skill_execute" not in types
    assert "tool_call" in types
    assert "tool_result" in types

    assert len(results) >= 1
    finding = results[0]
    assert "sentiment" in finding and finding["sentiment"] in (
        "positive",
        "negative",
        "neutral",
    )
    assert "summary" in finding and isinstance(finding["summary"], str)
