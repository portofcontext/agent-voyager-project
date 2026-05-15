"""`avp.cost.source` provenance on model_turn_ended + cost_recorded.

AVP stamps every cost number with one of:
  - `computed`: we did the math locally from the price table
  - `reported`: the API/SDK handed us the number directly
  - `unknown`: no price found AND no provider report (cost is 0.0)

Audit consumers filter / weight by this tag — a value tagged `unknown`
SHOULD page someone, while `computed` from a stale table is informational.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from avp_openai_agent import OpenAIAgentTranslator, descriptor

from avp import (
    Commission,
    CostRecordedEvent,
    ModelTurnEndedEvent,
)


@dataclass
class _Details:
    cached_tokens: int = 0


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int
    input_tokens_details: _Details = None  # type: ignore[assignment]


@dataclass
class _Resp:
    usage: _Usage
    output: list[Any]
    model: str = "gpt-5-nano"
    status: str = "completed"


class _FakeAgent:
    def __init__(self, model: str = "gpt-5-nano") -> None:
        self.name = "avp-agent"
        self.tools: list[Any] = []
        self.model = model


def _commission(**overrides: Any) -> Commission:
    base: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "cost-source-test",
        "model": "gpt-5-nano",
        "prompt": "hi",
    }
    base.update(overrides)
    return Commission.model_validate(base)


def _drive(c: Commission, response: _Resp) -> list[Any]:
    captured: list[Any] = []
    t = OpenAIAgentTranslator(c, on_event=captured.append, descriptor=descriptor())
    t._root_agent_name = "avp-agent"
    agent = _FakeAgent(model=c.model or "gpt-5-nano")
    asyncio.run(t.on_agent_start(None, agent))
    asyncio.run(t.on_llm_start(None, agent, None, []))
    asyncio.run(t.on_llm_end(None, agent, response))
    return captured


def test_cost_source_computed_for_known_model() -> None:
    captured = _drive(
        _commission(),
        _Resp(usage=_Usage(input_tokens=10, output_tokens=5), output=[]),
    )
    turn = next(ev for ev in captured if isinstance(ev, ModelTurnEndedEvent))
    assert turn.data.avp_cost_source == "computed"
    assert turn.data.avp_cost_usd > 0


def test_cost_source_unknown_for_unpriced_model() -> None:
    captured: list[Any] = []
    with pytest.warns(UserWarning, match="no price for model"):
        captured = _drive(
            _commission(model="future-model-xyz"),
            _Resp(
                usage=_Usage(input_tokens=10, output_tokens=5),
                output=[],
                model="future-model-xyz",
            ),
        )
    turn = next(ev for ev in captured if isinstance(ev, ModelTurnEndedEvent))
    assert turn.data.avp_cost_source == "unknown"
    assert turn.data.avp_cost_usd == 0.0


def test_cost_source_propagates_to_cost_recorded() -> None:
    """The cost_recorded event sits next to model_turn_ended and MUST
    carry the same provenance tag, so consumers joining the two events
    don't see a mismatch."""
    captured = _drive(
        _commission(),
        _Resp(usage=_Usage(input_tokens=10, output_tokens=5), output=[]),
    )
    turn = next(ev for ev in captured if isinstance(ev, ModelTurnEndedEvent))
    cost = next(ev for ev in captured if isinstance(ev, CostRecordedEvent))
    assert turn.data.avp_cost_source == cost.data.avp_cost_source


def test_cost_source_serialized_under_dotted_alias() -> None:
    """Wire spelling is `avp.cost.source` (dotted), matching the rest of
    the AVP attribute namespace. The Pydantic field is `avp_cost_source`
    but the JSON dump uses the dotted alias."""
    captured = _drive(
        _commission(),
        _Resp(usage=_Usage(input_tokens=10, output_tokens=5), output=[]),
    )
    turn = next(ev for ev in captured if isinstance(ev, ModelTurnEndedEvent))
    wire = turn.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert wire["data"]["avp.cost.source"] == "computed"
    assert "avp_cost_source" not in wire["data"]
