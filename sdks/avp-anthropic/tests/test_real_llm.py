"""Real-LLM smoke tests for the avp-anthropic SDK adapter.

Gated on `-m real_llm` + ANTHROPIC_API_KEY. These exercise the adapter's
two surfaces end-to-end against a real Claude model, no mocks:

  - `AnthropicModelDriver.step(...)` translates one real turn and the cost
    resolves against the bundled price table (the provider-keyed lookup
    that has silently regressed before).
  - `AnthropicTracedClient` wraps a real `messages.create` and emits a
    well-formed `run_requested` -> `agent_started` -> `assistant_message`
    -> `agent_stopped` trajectory.

The full agent loop (`run_agent`) is the reference agent's; its real-LLM
coverage lives with the supervisor example.
"""

from __future__ import annotations

import os

import pytest

from avp.commission import Commission, SupervisorPreamble
from avp_anthropic import AnthropicModelDriver, AnthropicTracedClient

SMOKE_MODEL = os.environ.get("AVP_SMOKE_MODEL", "claude-haiku-4-5-20251001")

pytestmark = pytest.mark.real_llm


def _require_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")


def test_driver_step_smoke_against_real_model() -> None:
    """One real turn through the driver: returns text, converges on
    end_turn, and resolves a non-zero computed cost for a known model."""
    _require_key()
    driver = AnthropicModelDriver(model=SMOKE_MODEL, max_tokens=64)
    mr = driver.step(
        [{"role": "user", "content": "Say 'AVP smoke test passes.' and nothing else."}]
    )
    assert mr.text is not None
    assert mr.converged is True
    assert mr.tokens_output > 0
    # Provider-keyed price lookup must resolve for a real Anthropic model.
    assert mr.cost_source == "computed"
    assert mr.cost_usd > 0


def test_traced_client_smoke_against_real_model() -> None:
    """A real `messages.create` through `AnthropicTracedClient` emits a
    well-formed trajectory bracketed by run_requested / agent_stopped."""
    _require_key()
    import anthropic

    commission = Commission(
        schema_version="0.1",
        run_id="real-llm-traced",
        model=SMOKE_MODEL,
        prompt="Say 'AVP smoke test passes.' and nothing else.",
        supervisor=SupervisorPreamble(name="avp-anthropic-real-llm-test", version="0.1"),
    )
    events: list = []
    with AnthropicTracedClient(
        anthropic.Anthropic(), commission=commission, on_event=events.append
    ) as client:
        resp = client.messages.create(
            model=SMOKE_MODEL,
            max_tokens=64,
            messages=[{"role": "user", "content": commission.prompt}],
        )
        if resp.stop_reason == "end_turn":
            client.converged()

    types = [type(e).__name__ for e in events]
    assert types[0] == "RunRequestedEvent"
    assert "AgentStartedEvent" in types
    assert "AssistantMessageEvent" in types
    assert types[-1] == "AgentStoppedEvent"
    assert events[-1].data.reason.value == "converged"
    am = next(e for e in events if type(e).__name__ == "AssistantMessageEvent")
    assert am.data.cost_usd > 0
    assert am.data.usage.output_tokens > 0
