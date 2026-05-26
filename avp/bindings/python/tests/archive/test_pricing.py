"""Pricing externalization + cost-source provenance.

The price table lives in `avp/data/prices.json` and is loaded by
`avp.load_default_prices()`. Both agent packages import from
`avp.compute_cost`, so a single table change covers them. Each
`model_turn_ended` event carries `avp.cost.source` tagging the
provenance of `avp.cost_usd` — `computed`, `reported`, or `unknown`.
"""

from __future__ import annotations

from avp.agent.agent import AVPAgent
from avp.agent.drivers import ModelResponse
from avp.agent.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from avp.commission import Commission
from avp.pricing import (
    COST_SOURCE_COMPUTED,
    COST_SOURCE_UNKNOWN,
    ModelPrice,
    compute_cost,
    load_default_prices,
)
from avp.trajectory import ModelTurnEndedEvent

# ── Default table loads from JSON ──────────────────────────────────────────


def test_default_prices_loads_from_data_file() -> None:
    prices = load_default_prices()
    # Sonnet 4.6 is bundled in the default ship; if this entry is missing
    # then the JSON loader is broken or the file shipped without it.
    assert "claude-sonnet-4-6" in prices
    sonnet = prices["claude-sonnet-4-6"]
    assert isinstance(sonnet, ModelPrice)
    assert sonnet.input == 3.0
    assert sonnet.output == 15.0


def test_load_returns_fresh_dict_on_each_call() -> None:
    """Mutating the returned dict MUST NOT affect later loads — callers
    can override individual entries without affecting other consumers."""
    a = load_default_prices()
    a["fake/model"] = ModelPrice(input=1.0, output=1.0)
    b = load_default_prices()
    assert "fake/model" not in b


# ── compute_cost: math + provenance ────────────────────────────────────────


def test_compute_cost_uses_per_million_pricing() -> None:
    prices = {"m1": ModelPrice(input=10.0, output=30.0, cache_read=1.0, cache_write=12.5)}
    cost, source = compute_cost(
        "m1",
        input_tokens=1_000_000,  # AVP convention: includes cache reads/writes
        output_tokens=500_000,
        cache_read=200_000,
        cache_write=100_000,
        prices=prices,
    )
    # fresh = 1M - 200k - 100k = 700k
    # cost  = 700k * 10/M + 200k * 1/M + 100k * 12.5/M + 500k * 30/M
    #       = 7.0 + 0.2 + 1.25 + 15.0 = 23.45
    assert abs(cost - 23.45) < 1e-9
    assert source == COST_SOURCE_COMPUTED


def test_compute_cost_returns_unknown_when_model_missing() -> None:
    cost, source = compute_cost(
        "not-in-table",
        input_tokens=100,
        output_tokens=10,
        cache_read=0,
        cache_write=0,
        prices={},
    )
    assert cost == 0.0
    assert source == COST_SOURCE_UNKNOWN


# ── Wire shape: avp.cost.source on model_turn_ended ────────────────────────


def test_model_turn_ended_emits_computed_when_driver_default() -> None:
    """The reference agent stamps `avp.cost.source` from
    `ModelResponse.cost_source`, defaulting to `computed`."""
    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="cost-default", model="test/mock"),
        model=ScriptedModel(
            [
                ModelResponse(
                    tokens_input=10,
                    tokens_output=5,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        ),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )
    agent.run()
    ended = next(e for e in agent.trajectory if isinstance(e, ModelTurnEndedEvent))
    assert ended.data.avp_cost_source == "computed"


def test_model_turn_ended_emits_reported_when_driver_says_so() -> None:
    """If a driver gets a cost number from the API directly, it sets
    `cost_source="reported"` and the agent forwards that
    verbatim — no recomputation, no override."""
    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="cost-prov", model="test/mock"),
        model=ScriptedModel(
            [
                ModelResponse(
                    tokens_input=10,
                    tokens_output=5,
                    cost_usd=0.99,
                    cost_source="reported",
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        ),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )
    agent.run()
    ended = next(e for e in agent.trajectory if isinstance(e, ModelTurnEndedEvent))
    assert ended.data.avp_cost_source == "reported"
    assert ended.data.avp_cost_usd == 0.99


def test_model_turn_ended_serializes_cost_source_under_dotted_alias() -> None:
    """Wire spelling is `avp.cost.source` (dotted), matching the rest
    of the AVP attribute namespace. Pydantic field is `avp_cost_source`."""
    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="cost-wire", model="test/mock"),
        model=ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        ),
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )
    agent.run()
    ended = next(e for e in agent.trajectory if isinstance(e, ModelTurnEndedEvent))
    wire = ended.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert wire["data"]["avp.cost.source"] == "computed"
    # Sanity: the pydantic field name does NOT leak into the wire dump.
    assert "avp_cost_source" not in wire["data"]
