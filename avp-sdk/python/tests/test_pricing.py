from datetime import UTC, datetime, timedelta

import pytest

from avp.commission import ModelRef
from avp.trajectory import Metrics
from avp.utils import pricing
from avp.utils.pricing import ModelPrice, Prices, compute_cost, load_prices, save_prices


def prices(fetched: datetime, **models: ModelPrice) -> Prices:
    return Prices(fetched=fetched, models={k.replace("__", "/"): v for k, v in models.items()})


NOW = datetime.now(UTC)
TABLE = prices(
    NOW,
    anthropic__claude_sonnet=ModelPrice(input=3, output=15, cache_read=0.3, cache_write=3.75),
    openai__gpt=ModelPrice(input=2, output=8),
)
SONNET = ModelRef(provider="anthropic", id="claude_sonnet")


def test_bundled_snapshot_ships_with_the_package():
    bundled = pricing.bundled_prices()
    assert bundled.models["anthropic/claude-sonnet-4-5"].output > 0


def test_compute_cost_uses_the_price_for_the_provider_and_model():
    m = 1_000_000
    assert (
        compute_cost(
            TABLE, "anthropic", "claude_sonnet", Metrics(prompt_tokens=m, completion_tokens=m)
        )
        == 18.0
    )
    assert (
        compute_cost(
            TABLE, "openrouter", "claude_sonnet", Metrics(prompt_tokens=m, completion_tokens=m)
        )
        is None
    )
    assert compute_cost(TABLE, "anthropic", "claude_sonnet", Metrics(prompt_tokens=m)) is None
    assert (
        compute_cost(
            TABLE, "anthropic", "claude_sonnet", Metrics(prompt_tokens=0, completion_tokens=0)
        )
        == 0.0
    )


def test_compute_cost_prices_cache_tokens():
    metrics = Metrics(
        prompt_tokens=1_000_000,
        completion_tokens=0,
        cached_tokens=400_000,
        extra={"avp": {"cache_creation_input_tokens": 100_000}},
    )
    cost = compute_cost(TABLE, "anthropic", "claude_sonnet", metrics)
    assert cost == pytest.approx((500_000 * 3 + 400_000 * 0.3 + 100_000 * 3.75) / 1_000_000)
    with pytest.raises(ValueError):
        compute_cost(
            TABLE,
            "anthropic",
            "claude_sonnet",
            Metrics(prompt_tokens=1, completion_tokens=0, cached_tokens=2),
        )


@pytest.fixture
def fetches(monkeypatch):
    calls = []

    def fake_fetch():
        calls.append(1)
        return TABLE

    monkeypatch.setattr(pricing, "fetch_prices", fake_fetch)
    return calls


def test_load_prices_from_a_path_never_fetches_without_max_age(tmp_path, fetches):
    with pytest.raises(FileNotFoundError):
        load_prices(tmp_path / "missing.json")
    path = save_prices(TABLE, tmp_path / "prices.json")
    assert load_prices(path) == TABLE
    assert fetches == []


def test_load_prices_refreshes_a_stale_or_missing_file_with_max_age(tmp_path, fetches):
    path = tmp_path / "prices.json"
    assert load_prices(path, max_age=timedelta(days=1)) == TABLE
    assert load_prices(path) == TABLE
    stale = TABLE.model_copy(update={"fetched": NOW - timedelta(days=2)})
    save_prices(stale, path)
    assert load_prices(path, max_age=timedelta(days=3)) == stale
    assert load_prices(path, max_age=timedelta(days=1)) == TABLE
    assert fetches == [1, 1]


def test_load_prices_without_path_uses_the_newer_of_cache_and_bundled(
    tmp_path, monkeypatch, fetches
):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    bundled = pricing.bundled_prices()
    assert load_prices() == bundled
    old = TABLE.model_copy(update={"fetched": bundled.fetched - timedelta(days=1)})
    save_prices(old)
    assert load_prices() == bundled
    save_prices(TABLE)
    assert load_prices() == TABLE
    assert fetches == []
