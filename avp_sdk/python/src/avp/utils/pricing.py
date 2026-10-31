"""Model prices from [models.dev](https://models.dev), for `cost_source: "computed"`.

The package ships a snapshot in `avp/utils/data/avp_prices.json`, refreshed each time
the package is published, so prices work offline with no setup. A caller that
wants newer prices passes `max_age` to `load_prices`, which fetches models.dev
when the prices are older than that and keeps them in a cache file. A caller
that wants the same costs on every rerun passes a file of its own.
"""

import json
import os
import urllib.request
from datetime import UTC, datetime, timedelta
from functools import cache
from importlib import resources
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from avp.commission import ModelRef
from avp.trajectory import CostSource

MODELS_DEV_API = "https://models.dev/api.json"


class ModelPrice(BaseModel):
    """One model's prices at one provider, in US dollars per million tokens."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float | None = Field(default=None, ge=0)
    """Absent when the provider doesn't charge for cache reads separately."""
    cache_write: float | None = Field(default=None, ge=0)
    """Absent when the provider doesn't charge for cache writes separately."""


class Prices(BaseModel):
    """Every priced model on models.dev, as the cache file stores it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = MODELS_DEV_API
    """Where the prices came from."""
    fetched: AwareDatetime
    """When they were fetched."""
    models: dict[str, ModelPrice]
    """Keyed by `"<provider>/<model id>"`, as models.dev names them."""


@cache
def bundled_prices() -> Prices:
    """The snapshot shipped in the package, as of its last publish."""
    data = resources.files("avp.utils").joinpath("data", "avp_prices.json").read_text()
    return Prices.model_validate_json(data)


def default_cache_path() -> Path:
    """`$XDG_CACHE_HOME/avp/avp_prices.json`, or `~/.cache/avp/avp_prices.json`
    when `XDG_CACHE_HOME` isn't set."""
    root = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(root) / "avp" / "avp_prices.json"


def fetch_prices() -> Prices:
    """Download models.dev and keep every model it prices. Needs network."""
    # models.dev answers 403 to urllib's default User-Agent.
    request = urllib.request.Request(MODELS_DEV_API, headers={"User-Agent": "avp-python-sdk"})
    with urllib.request.urlopen(request, timeout=30) as response:
        catalog = json.load(response)
    models: dict[str, ModelPrice] = {}
    for provider_id, provider in catalog.items():
        for model_id, model in provider.get("models", {}).items():
            cost = model.get("cost") or {}
            if cost.get("input") is None or cost.get("output") is None:
                continue
            models[f"{provider_id}/{model_id}"] = ModelPrice(
                input=cost["input"],
                output=cost["output"],
                cache_read=cost.get("cache_read"),
                cache_write=cost.get("cache_write"),
            )
    return Prices(fetched=datetime.now(UTC), models=dict(sorted(models.items())))


def save_prices(prices: Prices, path: Path | None = None) -> Path:
    """Write `prices` to `path` (default: `default_cache_path()`) and return the path."""
    path = path or default_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write a temporary file and rename it, so a reader never sees half a file.
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(prices.model_dump_json(indent=1, exclude_none=True) + "\n")
    partial.replace(path)
    return path


def load_prices(path: Path | None = None, *, max_age: timedelta | None = None) -> Prices:
    """The prices to compute costs with.

    Without `path`, the newer of the cache file at `default_cache_path()` and
    the bundled snapshot. With `path`, that file; a missing file raises
    `FileNotFoundError` unless `max_age` is set.

    With `max_age`, when the prices were fetched longer ago than that (or the
    file is missing), fetch models.dev, save the result to `path` (default:
    `default_cache_path()`), and return it. Without `max_age` this never calls
    models.dev, for a caller in a sandbox or one that refreshes the file itself
    with `fetch_prices` and `save_prices`.
    """
    file = path or default_cache_path()
    prices = Prices.model_validate_json(file.read_text()) if file.exists() else None
    if path is None:
        bundled = bundled_prices()
        if prices is None or bundled.fetched > prices.fetched:
            prices = bundled
    if max_age is not None and (prices is None or datetime.now(UTC) - prices.fetched > max_age):
        prices = fetch_prices()
        save_prices(prices, file)
    if prices is None:
        raise FileNotFoundError(file)
    return prices


def find_price(
    prices: Prices, model: ModelRef, response_model: str | None = None
) -> ModelPrice | None:
    """The price for `response_model` at `model.provider`, or for `model.id`
    when models.dev doesn't list `response_model`. None when it lists neither."""
    for model_id in (response_model, model.id):
        if model_id and (price := prices.models.get(f"{model.provider}/{model_id}")):
            return price
    return None


def compute_cost(
    prices: Prices,
    model: ModelRef,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    response_model: str | None = None,
    reported_cost_usd: float | None = None,
) -> tuple[float, CostSource]:
    """A response's `cost_usd` and `cost_source`, in the Trajectory spec's order:

    1. `reported_cost_usd` when the service or runtime reported one: `reported`.
    2. Otherwise the price from `find_price`, applied to the token counts: `computed`.
    3. Otherwise `0` and `unknown`.

    Token counts follow `Usage`: `input_tokens` includes the cache reads and
    writes. Cache tokens without a price of their own cost the input price.
    """
    if reported_cost_usd is not None:
        return reported_cost_usd, "reported"
    price = find_price(prices, model, response_model)
    if price is None:
        return 0.0, "unknown"
    uncached = input_tokens - cache_read_input_tokens - cache_creation_input_tokens
    if uncached < 0:
        raise ValueError("cache read and creation tokens exceed input_tokens")
    cache_read = price.input if price.cache_read is None else price.cache_read
    cache_write = price.input if price.cache_write is None else price.cache_write
    cost = (
        uncached * price.input
        + cache_read_input_tokens * cache_read
        + cache_creation_input_tokens * cache_write
        + output_tokens * price.output
    ) / 1_000_000
    return cost, "computed"
