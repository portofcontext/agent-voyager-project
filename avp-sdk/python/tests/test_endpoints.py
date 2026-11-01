from datetime import UTC, datetime, timedelta

import pytest

from avp.utils import _models_dev, endpoints
from avp.utils.endpoints import (
    BEARER,
    GAP_FILLERS,
    Auth,
    Endpoint,
    Endpoints,
    default_base_url,
    fetch_endpoints,
    load_endpoints,
    provider_auth,
    save_endpoints,
)

CATALOG = {
    "openrouter": {"api": "https://openrouter.ai/api/v1", "npm": "@openrouter/ai-sdk-provider"},
    "anthropic": {"npm": "@ai-sdk/anthropic"},
    "openai": {"api": "https://example.test/openai/v1", "npm": "@ai-sdk/openai"},
    "databricks": {
        "api": "https://${DATABRICKS_HOST}/ai-gateway/mlflow/v1",
        "npm": "@ai-sdk/openai-compatible",
    },
    "google-vertex": {"npm": "@ai-sdk/google-vertex"},
    "mystery": {"api": "https://mystery.test/v1", "npm": "mystery-provider"},
}


def test_the_bundled_snapshot_fills_the_gaps():
    bundled = endpoints.bundled_endpoints()
    assert default_base_url(bundled, "anthropic") == GAP_FILLERS["anthropic"]
    assert default_base_url(bundled, "openrouter") == "https://openrouter.ai/api/v1"
    assert default_base_url(bundled, "amazon-bedrock") is None


def test_the_bundled_snapshot_knows_where_keys_go():
    bundled = endpoints.bundled_endpoints()
    assert provider_auth(bundled, "anthropic") == Auth(header="x-api-key")
    assert provider_auth(bundled, "google") == Auth(header="x-goog-api-key")
    assert provider_auth(bundled, "openrouter") == BEARER
    assert provider_auth(bundled, "amazon-bedrock") == BEARER
    assert provider_auth(bundled, "google-vertex") is None
    assert provider_auth(bundled, "no-such-provider") is None


def test_fetch_keeps_models_dev_first_and_reads_auth_from_the_package(monkeypatch):
    monkeypatch.setattr(_models_dev, "fetch_catalog", lambda: CATALOG)
    fetched = fetch_endpoints(
        fill={"anthropic": "https://a.test/v1", "openai": "https://o.test/v1"}
    )
    assert fetched.providers == {
        "anthropic": Endpoint(base_url="https://a.test/v1", auth=Auth(header="x-api-key")),
        # A placeholder URL is dropped, but the auth is still known.
        "databricks": Endpoint(auth=BEARER),
        "mystery": Endpoint(base_url="https://mystery.test/v1"),
        "openai": Endpoint(base_url="https://example.test/openai/v1", auth=BEARER),
        "openrouter": Endpoint(base_url="https://openrouter.ai/api/v1", auth=BEARER),
    }


@pytest.fixture
def fetches(monkeypatch):
    calls = []
    table = Endpoints(
        fetched=datetime.now(UTC), providers={"x": Endpoint(base_url="https://x.test")}
    )

    def fake_fetch() -> Endpoints:
        calls.append(True)
        return table

    monkeypatch.setattr(endpoints, "fetch_endpoints", fake_fetch)
    return calls, table


def test_load_uses_a_file_and_refreshes_it_only_with_max_age(tmp_path, fetches):
    calls, table = fetches
    path = tmp_path / "endpoints.json"
    with pytest.raises(FileNotFoundError):
        load_endpoints(path)
    assert load_endpoints(path, max_age=timedelta(days=1)) == table
    stale = Endpoints(fetched=datetime.now(UTC) - timedelta(days=2), providers={})
    save_endpoints(stale, path)
    assert load_endpoints(path) == stale
    assert load_endpoints(path, max_age=timedelta(days=1)) == table
    assert len(calls) == 2


def test_load_without_path_uses_the_newer_of_cache_and_bundled(tmp_path, monkeypatch, fetches):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    bundled = endpoints.bundled_endpoints()
    assert load_endpoints() == bundled
    newer = Endpoints(fetched=bundled.fetched + timedelta(days=1), providers={})
    save_endpoints(newer)
    assert load_endpoints() == newer
    assert (tmp_path / "avp" / "avp_endpoints.json").exists()
