"""Shared pricing for AVP agents.

Why this lives in `avp` core, not per-agent:
- Both `avp-anthropic` and `avp-claude-agent-sdk` need the same model-price
  lookup. Two copies drift the moment Anthropic ships new pricing.
- The price table is data, not policy — agents load it at startup,
  users can override via the public `PriceTable` type, and the on-wire
  cost number is tagged with `avp.cost.source` so downstreams can tell
  a locally-computed number from a provider-reported one (or unknown).

Default ships in `avp/data/prices.json`; `load_default_prices()` reads it
fresh on each call. To override, pass a `PriceTable` to your driver /
translator at construction.

`COST_SOURCE_*` constants name the audit-source values:
  - `computed`: we did the math locally from a price table
  - `reported`: the API/SDK handed us the number directly
  - `unknown`: no price found and no provider report (cost reported as 0.0)

The agent stamps `avp.cost.source` on `model_turn_ended` and
`cost_recorded` events so trajectory consumers can filter / weight by
provenance — e.g. an audit pipeline that trusts reported numbers but
flags computed numbers from a stale price table.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Literal

CostSource = Literal["computed", "reported", "unknown"]

COST_SOURCE_COMPUTED: CostSource = "computed"
COST_SOURCE_REPORTED: CostSource = "reported"
COST_SOURCE_UNKNOWN: CostSource = "unknown"


@dataclass(frozen=True)
class ModelPrice:
    """Per-1M-token pricing in USD."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


PriceTable = Mapping[str, ModelPrice]


def load_default_prices() -> dict[str, ModelPrice]:
    """Load the bundled default price table from `avp/data/prices.json`.

    Reads on each call so users who patch the file in-place get fresh
    numbers without restarting their process. Returns a fresh dict;
    callers can mutate without side effects.
    """
    raw = resources.files("avp.data").joinpath("prices.json").read_text()
    parsed = json.loads(raw)
    return {
        model: ModelPrice(
            input=float(spec["input"]),
            output=float(spec["output"]),
            cache_read=float(spec.get("cache_read", 0.0)),
            cache_write=float(spec.get("cache_write", 0.0)),
        )
        for model, spec in parsed.get("models", {}).items()
    }


def compute_cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_write: int,
    prices: PriceTable,
) -> tuple[float, CostSource]:
    """Compute billable USD cost from a turn's token counts.

    Returns `(cost, source)` so callers can stamp `avp.cost.source` on
    the wire alongside `avp.cost_usd`.

    `input_tokens` here is the AVP convention (cache reads INCLUDED).
    Cache reads / writes are billed at their own per-token rates; the
    fresh portion gets the regular input rate. If the model isn't in
    the table, returns `(0.0, "unknown")` — caller should warn so
    silent under-counts don't ship.
    """
    p = prices.get(model)
    if p is None:
        return 0.0, COST_SOURCE_UNKNOWN
    fresh = max(0, input_tokens - cache_read - cache_write)
    cost = (
        fresh * p.input / 1_000_000
        + cache_read * p.cache_read / 1_000_000
        + cache_write * p.cache_write / 1_000_000
        + output_tokens * p.output / 1_000_000
    )
    return cost, COST_SOURCE_COMPUTED
