"""Model prices from [models.dev](https://models.dev), for `cost_source: "computed"`.

The package ships a snapshot in `avp/utils/data/avp_prices.json`, refreshed each time
the package is published, so prices work offline with no setup. A caller that
wants newer prices passes `max_age` to `load_prices`, which fetches models.dev
when the prices are older than that and keeps them in a cache file. A caller
that wants the same costs on every rerun passes a file of its own.
"""

from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from avp.trajectory import Metrics
from avp.utils import _models_dev
from avp.utils._models_dev import Snapshot

FILE = "avp_prices.json"


class ModelPrice(BaseModel):
    """One model's prices at one provider, in US dollars per million tokens."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float | None = Field(default=None, ge=0)
    """Absent when the provider doesn't charge for cache reads separately."""
    cache_write: float | None = Field(default=None, ge=0)
    """Absent when the provider doesn't charge for cache writes separately."""


class Prices(Snapshot):
    """Every priced model on models.dev, as the cache file stores it."""

    models: dict[str, ModelPrice]
    """Keyed by `"<provider>/<model id>"`, as models.dev names them."""


@cache
def bundled_prices() -> Prices:
    """The snapshot shipped in the package, as of its last publish."""
    return _models_dev.bundled(Prices, FILE)


def default_cache_path() -> Path:
    """`$XDG_CACHE_HOME/avp/avp_prices.json`, or `~/.cache/avp/avp_prices.json`
    when `XDG_CACHE_HOME` isn't set."""
    return _models_dev.cache_path(FILE)


def fetch_prices(catalog: dict[str, Any] | None = None) -> Prices:
    """Download models.dev and keep every model it prices. Needs network, unless
    `catalog` is models.dev's catalog already downloaded."""
    models: dict[str, ModelPrice] = {}
    for provider_id, provider in (catalog or _models_dev.fetch_catalog()).items():
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
    return _models_dev.save(prices, path or default_cache_path())


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
    return _models_dev.load(
        Prices,
        path,
        default_path=default_cache_path(),
        bundled=bundled_prices,
        fetch=lambda: fetch_prices(),
        max_age=max_age,
    )


def compute_cost(prices: Prices, provider: str, model_name: str, metrics: Metrics) -> float | None:
    """A response's `cost_usd` from the models.dev price for `provider` and
    `model_name`, applied to the response's `metrics`. None when models.dev
    doesn't list the model or the metrics have no `prompt_tokens` and
    `completion_tokens`.

    Cached and cache creation tokens are part of `prompt_tokens`. Without a
    price of their own they cost the input price.
    """
    price = prices.models.get(f"{provider}/{model_name}")
    if price is None or metrics.prompt_tokens is None or metrics.completion_tokens is None:
        return None
    avp = metrics.extra.avp if metrics.extra is not None else None
    cache_read_tokens = metrics.cached_tokens or 0
    cache_write_tokens = (avp.cache_creation_input_tokens if avp else None) or 0
    uncached = metrics.prompt_tokens - cache_read_tokens - cache_write_tokens
    if uncached < 0:
        raise ValueError("cached and cache creation tokens exceed prompt_tokens")
    cache_read = price.input if price.cache_read is None else price.cache_read
    cache_write = price.input if price.cache_write is None else price.cache_write
    return (
        uncached * price.input
        + cache_read_tokens * cache_read
        + cache_write_tokens * cache_write
        + metrics.completion_tokens * price.output
    ) / 1_000_000
