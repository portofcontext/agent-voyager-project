"""Anthropic refusal detection.

Verified against the public Messages API docs as of 2026-05:
  - `stop_reason="refusal"` is the documented refusal value
  - `stop_reason="sensitive"` is observed in the wild but not yet in
    the public docs (defensive support — it surfaces today, undocumented)

Both flow into `ModelResponse.refusal` with `provider="anthropic"`. The
runner emits `aep.refusal_recorded` and stops with `StopReason.refused`.
"""

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
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_stop_reason_refusal_populates_response_refusal() -> None:
    resp = _mock_response(
        content=[{"type": "text", "text": "I can't help with that request."}],
        usage={"input_tokens": 10, "output_tokens": 8},
        stop_reason="refusal",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "do the bad thing"}])
    assert out.refusal is not None
    assert out.refusal.reason == "refusal"
    assert out.refusal.provider == "anthropic"
    assert out.refusal.message == "I can't help with that request."
    # Anthropic doesn't expose a category enum.
    assert out.refusal.category is None
    # Refusal turns should not be marked converged — the runner treats
    # refused as a distinct terminal state.
    assert out.converged is False


def test_stop_reason_sensitive_also_treated_as_refusal() -> None:
    """`sensitive` is observed in the wild but not documented. Defensive
    support keeps audit logs honest until Anthropic publishes the value."""
    resp = _mock_response(
        content=[{"type": "text", "text": "That topic is sensitive."}],
        usage={"input_tokens": 10, "output_tokens": 5},
        stop_reason="sensitive",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert out.refusal is not None
    assert out.refusal.reason == "sensitive"
    assert out.refusal.provider == "anthropic"


def test_explicit_refusal_content_block_renders_into_message() -> None:
    """If the response body carries an explicit refusal-typed content
    block, its text wins over plain text blocks for the `message`
    field. Anthropic has been seen returning refusal-typed blocks."""
    resp = _mock_response(
        content=[
            {"type": "refusal", "text": "Refused: policy violation."},
        ],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="refusal",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert out.refusal is not None
    assert "policy violation" in out.refusal.message


def test_no_message_text_means_refusal_message_is_none() -> None:
    resp = _mock_response(
        content=[],
        usage={"input_tokens": 5, "output_tokens": 0},
        stop_reason="refusal",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert out.refusal is not None
    assert out.refusal.message is None


def test_normal_stop_reason_does_not_set_refusal() -> None:
    """Backwards-compat: end_turn / tool_use / max_tokens / stop_sequence
    MUST NOT populate `refusal`. Only refusal-flavored stop_reasons
    trigger the field."""
    for stop_reason in ("end_turn", "tool_use", "max_tokens", "stop_sequence", "pause_turn"):
        resp = _mock_response(
            content=[{"type": "text", "text": "ok"}],
            usage={"input_tokens": 5, "output_tokens": 5},
            stop_reason=stop_reason,
        )
        driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
        out = driver.step([{"role": "user", "content": "x"}])
        assert out.refusal is None, f"stop_reason={stop_reason} should not be a refusal"
