"""Driver-translation tests for AnthropicModelDriver. Uses a mock Anthropic
client so we don't hit the network or burn API credits."""

from __future__ import annotations

from types import SimpleNamespace

from aep_anthropic import AnthropicModelDriver


def _mock_response(*, content: list[dict], usage: dict, stop_reason: str) -> SimpleNamespace:
    blocks = [SimpleNamespace(**b) for b in content]
    return SimpleNamespace(content=blocks, usage=SimpleNamespace(**usage), stop_reason=stop_reason)


class _MockClient:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []
        self.messages = self  # so client.messages.create works

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_text_only_response_sets_converged_when_end_turn() -> None:
    resp = _mock_response(
        content=[{"type": "text", "text": "all done"}],
        usage={"input_tokens": 100, "output_tokens": 25},
        stop_reason="end_turn",
    )
    client = _MockClient(resp)
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=client)

    out = driver.step([{"role": "user", "content": "hi"}])

    assert out.text == "all done"
    assert out.tool_calls == []
    assert out.converged is True
    assert out.tokens_input == 100  # no cache → equal to fresh input
    assert out.tokens_output == 25
    # 100 input @ $3/M + 25 output @ $15/M = 0.0003 + 0.000375 = 0.000675
    assert abs(out.cost_usd - 0.000675) < 1e-9


def test_tool_use_response_translates_to_tool_calls() -> None:
    resp = _mock_response(
        content=[
            {"type": "text", "text": "I'll run a command."},
            {"type": "tool_use", "id": "toolu_01", "name": "bash", "input": {"command": "ls"}},
        ],
        usage={"input_tokens": 50, "output_tokens": 30},
        stop_reason="tool_use",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))

    out = driver.step([{"role": "user", "content": "list files"}])

    assert out.text == "I'll run a command."
    assert len(out.tool_calls) == 1
    tc = out.tool_calls[0]
    assert tc.call_id == "toolu_01"
    assert tc.tool == "bash"
    assert tc.input == {"command": "ls"}
    assert out.converged is False  # tool_use → continue


def test_cache_read_tokens_count_as_input_per_aep_convention() -> None:
    """AEP §10.4: tokens_input INCLUDES cache-read tokens. The Anthropic SDK
    reports input_tokens as fresh-only; the driver MUST add cache reads back."""
    resp = _mock_response(
        content=[{"type": "text", "text": "ok"}],
        usage={
            "input_tokens": 50,
            "output_tokens": 10,
            "cache_read_input_tokens": 400,
            "cache_creation_input_tokens": 0,
        },
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))

    out = driver.step([{"role": "user", "content": "x"}])

    # AEP wire: tokens_input = 50 fresh + 400 cache_read = 450
    assert out.tokens_input == 450
    assert out.tokens_cache_read == 400
    # Cost: 50 fresh × $3/M + 400 cache_read × $0.30/M + 10 output × $15/M
    expected = 50 * 3 / 1_000_000 + 400 * 0.30 / 1_000_000 + 10 * 15 / 1_000_000
    assert abs(out.cost_usd - expected) < 1e-9


def test_unknown_model_falls_back_to_zero_cost(recwarn) -> None:
    resp = _mock_response(
        content=[{"type": "text", "text": "ok"}],
        usage={"input_tokens": 10, "output_tokens": 5},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-future-99", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert out.cost_usd == 0.0
    assert any("no price for model" in str(w.message) for w in recwarn.list)


def test_history_translates_system_user_assistant_tool() -> None:
    resp = _mock_response(
        content=[{"type": "text", "text": "thanks"}],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="end_turn",
    )
    client = _MockClient(resp)
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=client)

    history = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Run ls."},
        {"role": "assistant", "content": "ok"},
        {"role": "tool", "tool": "bash", "call_id": "toolu_01", "output": "file1\nfile2"},
    ]
    driver.step(history)

    call = client.calls[-1]
    assert call["system"] == "You are helpful."
    assert call["messages"][0] == {"role": "user", "content": "Run ls."}
    assert call["messages"][1] == {"role": "assistant", "content": "ok"}
    tool_msg = call["messages"][2]
    assert tool_msg["role"] == "user"
    assert tool_msg["content"][0]["type"] == "tool_result"
    assert tool_msg["content"][0]["tool_use_id"] == "toolu_01"
    assert tool_msg["content"][0]["content"] == "file1\nfile2"
