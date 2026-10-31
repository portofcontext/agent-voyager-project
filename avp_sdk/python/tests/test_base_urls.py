from datetime import UTC, datetime, timedelta

import pytest

from avp.utils import _models_dev, base_urls
from avp.utils.base_urls import (
    GAP_FILLERS,
    BaseUrls,
    default_base_url,
    fetch_base_urls,
    load_base_urls,
    save_base_urls,
)

CATALOG = {
    "openrouter": {"api": "https://openrouter.ai/api/v1"},
    "anthropic": {},
    "openai": {"api": "https://example.test/openai/v1"},
    "databricks": {"api": "https://${DATABRICKS_HOST}/ai-gateway/mlflow/v1"},
}


def test_the_bundled_snapshot_fills_the_gaps():
    bundled = base_urls.bundled_base_urls()
    assert default_base_url(bundled, "anthropic") == GAP_FILLERS["anthropic"]
    assert default_base_url(bundled, "openrouter") == "https://openrouter.ai/api/v1"
    assert default_base_url(bundled, "amazon-bedrock") is None


def test_fetch_keeps_models_dev_first_and_skips_placeholders(monkeypatch):
    monkeypatch.setattr(_models_dev, "fetch_catalog", lambda: CATALOG)
    fetched = fetch_base_urls(
        fill={"anthropic": "https://a.test/v1", "openai": "https://o.test/v1"}
    )
    assert fetched.providers == {
        "anthropic": "https://a.test/v1",
        "openai": "https://example.test/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }


@pytest.fixture
def fetches(monkeypatch):
    calls = []
    table = BaseUrls(fetched=datetime.now(UTC), providers={"x": "https://x.test"})

    def fake_fetch() -> BaseUrls:
        calls.append(True)
        return table

    monkeypatch.setattr(base_urls, "fetch_base_urls", fake_fetch)
    return calls, table


def test_load_uses_a_file_and_refreshes_it_only_with_max_age(tmp_path, fetches):
    calls, table = fetches
    path = tmp_path / "urls.json"
    with pytest.raises(FileNotFoundError):
        load_base_urls(path)
    assert load_base_urls(path, max_age=timedelta(days=1)) == table
    stale = BaseUrls(fetched=datetime.now(UTC) - timedelta(days=2), providers={})
    save_base_urls(stale, path)
    assert load_base_urls(path) == stale
    assert load_base_urls(path, max_age=timedelta(days=1)) == table
    assert len(calls) == 2


def test_load_without_path_uses_the_newer_of_cache_and_bundled(tmp_path, monkeypatch, fetches):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    bundled = base_urls.bundled_base_urls()
    assert load_base_urls() == bundled
    newer = BaseUrls(fetched=bundled.fetched + timedelta(days=1), providers={})
    save_base_urls(newer)
    assert load_base_urls() == newer
    assert (tmp_path / "avp" / "avp_base_urls.json").exists()
