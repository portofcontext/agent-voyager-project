"""Anthropic extended-thinking blocks → ModelResponse.reasoning_blocks.

The driver MUST surface `thinking` and `redacted_thinking` content
blocks so the agent can emit `reasoning_emitted` events for each.
This test pins the block-shape we expect, so an SDK-version drift
that renames a field surfaces here instead of as a silent regression.
"""

from __future__ import annotations

from types import SimpleNamespace

from avp_anthropic import AnthropicModelDriver


def _mock_response(*, content: list[dict], usage: dict, stop_reason: str) -> SimpleNamespace:
    blocks = [SimpleNamespace(**b) for b in content]
    return SimpleNamespace(content=blocks, usage=SimpleNamespace(**usage), stop_reason=stop_reason)


class _MockClient:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_thinking_block_becomes_reasoning_block() -> None:
    """Anthropic returns plain `thinking` blocks with `thinking` (text)
    and `signature` fields. The driver maps those to a non-redacted
    ReasoningBlock."""
    resp = _mock_response(
        content=[
            {"type": "thinking", "thinking": "let me reason", "signature": "sig-1"},
            {"type": "text", "text": "answer"},
        ],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert len(out.reasoning_blocks) == 1
    rb = out.reasoning_blocks[0]
    assert rb.text == "let me reason"
    assert rb.signature == "sig-1"
    assert rb.redacted is False
    # Text block still produces text — unchanged.
    assert out.text == "answer"


def test_redacted_thinking_block_becomes_redacted_reasoning_block() -> None:
    """Encrypted-only thinking carries no `thinking` field; the
    `data` field holds the encrypted blob and we surface it as the
    signature so audit consumers can correlate replays across turns.
    `redacted=True` flags the absence of plaintext."""
    resp = _mock_response(
        content=[
            {"type": "redacted_thinking", "data": "blob-xyz"},
            {"type": "text", "text": "ok"},
        ],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert len(out.reasoning_blocks) == 1
    rb = out.reasoning_blocks[0]
    assert rb.text == ""
    assert rb.signature == "blob-xyz"
    assert rb.redacted is True


def test_multiple_thinking_blocks_each_recorded() -> None:
    resp = _mock_response(
        content=[
            {"type": "thinking", "thinking": "first", "signature": None},
            {"type": "text", "text": "interlude"},
            {"type": "thinking", "thinking": "second", "signature": None},
            {"type": "text", "text": "done"},
        ],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert [rb.text for rb in out.reasoning_blocks] == ["first", "second"]
    # Text from BOTH text blocks concatenates per existing behavior.
    assert out.text == "interludedone"


def test_no_thinking_blocks_means_empty_reasoning_blocks() -> None:
    resp = _mock_response(
        content=[{"type": "text", "text": "hi"}],
        usage={"input_tokens": 1, "output_tokens": 1},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert out.reasoning_blocks == []
