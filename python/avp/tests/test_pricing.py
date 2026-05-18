"""Pricing helper: loader fresh-copy semantics and compute_cost math.

Wire-shape tests for `avp.cost.source` on `assistant_message` live with
the agent packages that emit those events; this module covers only the
pure pricing API.
"""

from __future__ import annotations

from avp.pricing import (
    COST_SOURCE_COMPUTED,
    COST_SOURCE_UNKNOWN,
    ModelPrice,
    compute_cost,
    load_default_prices,
)


def test_default_prices_loads_from_data_file() -> None:
    prices = load_default_prices()
    assert "claude-sonnet-4-6" in prices
    sonnet = prices["claude-sonnet-4-6"]
    assert isinstance(sonnet, ModelPrice)
    assert sonnet.input == 3.0
    assert sonnet.output == 15.0


def test_load_returns_fresh_dict_on_each_call() -> None:
    a = load_default_prices()
    a["fake/model"] = ModelPrice(input=1.0, output=1.0)
    b = load_default_prices()
    assert "fake/model" not in b


def test_compute_cost_uses_per_million_pricing() -> None:
    prices = {"m1": ModelPrice(input=10.0, output=30.0, cache_read=1.0, cache_write=12.5)}
    cost, source = compute_cost(
        "m1",
        input_tokens=1_000_000,
        output_tokens=500_000,
        cache_read=200_000,
        cache_write=100_000,
        prices=prices,
    )
    # fresh = 1M - 200k - 100k = 700k
    # 700k*10/M + 200k*1/M + 100k*12.5/M + 500k*30/M = 7.0 + 0.2 + 1.25 + 15.0 = 23.45
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
