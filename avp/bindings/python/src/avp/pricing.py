"""Shared pricing for AVP agents.

Why this lives in `avp` core, not per-agent:
- Anthropic models are reachable through nearly every mainstream agent
  SDK: the raw Anthropic SDK, the Claude Agent SDK, LangChain /
  LangGraph, LlamaIndex, Pydantic AI, the OpenAI-compatible surfaces on
  Bedrock and Vertex, plus the long tail of provider-agnostic
  frameworks. Every AVP adapter that wraps one of these SDKs needs the
  same model-price lookup; a per-adapter copy drifts the moment
  Anthropic ships new pricing.
- The price table is data, not policy. Adapters load it at startup,
  users can override via the public `PriceTable` type, and the on-wire
  cost number is tagged with `avp.cost.source` so downstreams can tell
  a locally-computed number from a provider-reported one (or unknown).

Default ships in `avp/data/prices.json`, mirrored from models.dev and
keyed by its `<provider>/<model>` id (synced by `scripts/sync-prices.py`);
`load_default_prices()` reads it fresh on each call. `compute_cost`
normalizes a wire model (plus its provider) to a key here. To override,
pass a `PriceTable` to your driver / translator at construction.

`COST_SOURCE_*` constants name the audit-source values:
  - `computed`: we did the math locally from a price table
  - `reported`: the API/SDK handed us the number directly
  - `unknown`: no price found and no provider report (cost reported as 0.0)

The agent stamps `avp.cost.source` on each `assistant_message` event so
trajectory consumers can filter / weight by provenance, e.g. an audit
pipeline that trusts reported numbers but flags computed numbers from a
stale price table.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CostSource = Literal["computed", "reported", "unknown"]

COST_SOURCE_COMPUTED: CostSource = "computed"
COST_SOURCE_REPORTED: CostSource = "reported"
COST_SOURCE_UNKNOWN: CostSource = "unknown"


class ModelPrice(BaseModel):
    """Per-1M-token pricing in USD."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float = Field(default=0.0, ge=0)
    cache_write: float = Field(default=0.0, ge=0)


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
        model: ModelPrice.model_validate(spec) for model, spec in parsed.get("models", {}).items()
    }


def resolve_price(prices: PriceTable, model: str, provider: str | None = None) -> ModelPrice | None:
    """Resolve a price by the model the agent put on the wire.

    The bundled table is mirrored from models.dev and keyed by its
    `<provider>/<model>` id. A wire `model` is either a slug already
    containing a provider (`openai/gpt-4o`, used as-is) or a bare
    provider-native string (`claude-sonnet-4-6`) qualified with
    `provider` to form the key (`anthropic/claude-sonnet-4-6`). The
    exact string is tried first so a custom table keyed by bare names
    still works.

    Gateway caveat: the key is the model's origin slug, so when a Commission
    routes a model through a different storefront (`model: "openai/gpt-4o"` with
    `provider.id: "openrouter"`), this returns the model's *list* price, not the
    gateway's actual price (gateways add margin). Treat the result as a
    best-effort estimate and prefer provider-reported cost when available
    (`avp.cost.source = "reported"`).
    """
    p = prices.get(model)
    if p is not None:
        return p
    if provider and "/" not in model:
        return prices.get(f"{provider}/{model}")
    return None


def compute_cost(
    model: str,
    *,
    provider: str | None = None,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_write: int,
    prices: PriceTable,
) -> tuple[float, CostSource]:
    """Compute billable USD cost from a turn's token counts.

    Returns `(cost, source)` so callers can stamp `avp.cost.source` on
    the wire alongside `avp.cost_usd`.

    `provider` is the model's provider (e.g. `"anthropic"`), used to
    resolve a bare wire model against the `<provider>/<model>`-keyed
    table; omit it if the wire model is already provider-qualified.

    `input_tokens` here is the AVP convention (cache reads INCLUDED).
    Cache reads / writes are billed at their own per-token rates; the
    fresh portion gets the regular input rate. If the model isn't in
    the table, returns `(0.0, "unknown")` — caller should warn so
    silent under-counts don't ship.
    """
    p = resolve_price(prices, model, provider)
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
