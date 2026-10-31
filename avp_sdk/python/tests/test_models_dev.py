from datetime import UTC, datetime, timedelta

import pytest

from avp import models_dev
from avp.commission import ModelRef
from avp.models_dev import ModelPrice, Prices, compute_cost, find_price, load_prices, save_prices


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
    bundled = models_dev.bundled_prices()
    assert bundled.models["anthropic/claude-sonnet-4-5"].output > 0


def test_find_price_prefers_response_model_then_falls_back_to_model_id():
    dated = TABLE.model_copy(
        update={
            "models": {
                **TABLE.models,
                "anthropic/claude_sonnet-2026": ModelPrice(input=1, output=1),
            }
        }
    )
    assert find_price(dated, SONNET, "claude_sonnet-2026") == ModelPrice(input=1, output=1)
    assert (
        find_price(TABLE, SONNET, "claude_sonnet-2026") == TABLE.models["anthropic/claude_sonnet"]
    )
    assert find_price(TABLE, ModelRef(provider="openrouter", id="claude_sonnet")) is None


def test_compute_cost_follows_the_spec_order():
    m = 1_000_000
    assert compute_cost(TABLE, SONNET, reported_cost_usd=0.5, input_tokens=m, output_tokens=m) == (
        0.5,
        "reported",
    )
    assert compute_cost(TABLE, SONNET, input_tokens=m, output_tokens=m) == (18.0, "computed")
    missing = ModelRef(provider="anthropic", id="nope")
    assert compute_cost(TABLE, missing, input_tokens=m, output_tokens=m) == (0.0, "unknown")
    assert compute_cost(TABLE, SONNET, input_tokens=0, output_tokens=0) == (0.0, "computed")


def test_compute_cost_prices_cache_tokens():
    cost, _ = compute_cost(
        TABLE,
        SONNET,
        input_tokens=3_000_000,
        output_tokens=0,
        cache_read_input_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000,
    )
    assert cost == pytest.approx(3 + 0.3 + 3.75)
    # No cache prices of its own: cache tokens cost the input price.
    gpt = ModelRef(provider="openai", id="gpt")
    cost, _ = compute_cost(
        TABLE, gpt, input_tokens=2_000_000, output_tokens=0, cache_read_input_tokens=1_000_000
    )
    assert cost == pytest.approx(4.0)
    with pytest.raises(ValueError):
        compute_cost(TABLE, SONNET, input_tokens=1, output_tokens=0, cache_read_input_tokens=2)


@pytest.fixture
def fetches(monkeypatch):
    calls = []

    def fake_fetch():
        calls.append(1)
        return TABLE

    monkeypatch.setattr(models_dev, "fetch_prices", fake_fetch)
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
    bundled = models_dev.bundled_prices()
    assert load_prices() == bundled
    old = TABLE.model_copy(update={"fetched": bundled.fetched - timedelta(days=1)})
    save_prices(old)
    assert load_prices() == bundled
    save_prices(TABLE)
    assert load_prices() == TABLE
    assert fetches == []
