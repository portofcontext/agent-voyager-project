"""Each provider's default `base_url` and the header its API key goes in, for
sandbox egress, metering, or a credential proxy.

URLs come from models.dev's `api`, with `GAP_FILLERS` for providers it omits.
Auth comes from the provider's `npm` package via `AUTH_BY_PACKAGE`. Snapshots
work as in `avp.utils.pricing`.
"""

from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from avp.utils import _models_dev
from avp.utils._models_dev import Snapshot

FILE = "avp_endpoints.json"

GAP_FILLERS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "cohere": "https://api.cohere.com/v2",
    "google": "https://generativelanguage.googleapis.com/v1beta",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openai": "https://api.openai.com/v1",
    "perplexity": "https://api.perplexity.ai",
    "togetherai": "https://api.together.xyz/v1",
    "xai": "https://api.x.ai/v1",
}
"""Default URLs for providers models.dev gives no `api`."""


class Auth(BaseModel):
    """Where a provider's API key goes in a request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    header: str
    """Lowercase header name."""
    prefix: str = ""
    """Text before the key, such as `"Bearer "`."""


BEARER = Auth(header="authorization", prefix="Bearer ")

AUTH_BY_PACKAGE: dict[str, Auth] = {
    "@ai-sdk/anthropic": Auth(header="x-api-key"),
    "@ai-sdk/azure": Auth(header="api-key"),
    "@ai-sdk/google": Auth(header="x-goog-api-key"),
    # Bedrock API keys only; SigV4 can't go through a proxy.
    "@ai-sdk/amazon-bedrock": BEARER,
    "@ai-sdk/cerebras": BEARER,
    "@ai-sdk/cohere": BEARER,
    "@ai-sdk/deepinfra": BEARER,
    "@ai-sdk/gateway": BEARER,
    "@ai-sdk/groq": BEARER,
    "@ai-sdk/mistral": BEARER,
    "@ai-sdk/openai": BEARER,
    "@ai-sdk/openai-compatible": BEARER,
    "@ai-sdk/perplexity": BEARER,
    "@ai-sdk/togetherai": BEARER,
    "@ai-sdk/xai": BEARER,
    "@openrouter/ai-sdk-provider": BEARER,
}
"""Packages whose key is a fixed header value. Others, such as
`@ai-sdk/google-vertex`, are left out."""


class Endpoint(BaseModel):
    """One provider's defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str | None = None
    """None when it depends on the account or region."""
    auth: Auth | None = None
    """None when a proxy can't add the key."""


class Endpoints(Snapshot):
    """Each provider's defaults."""

    providers: dict[str, Endpoint]
    """Keyed by a Model's `provider`."""


@cache
def bundled_endpoints() -> Endpoints:
    """The snapshot shipped in the package."""
    return _models_dev.bundled(Endpoints, FILE)


def default_cache_path() -> Path:
    """`avp/avp_endpoints.json` under `$XDG_CACHE_HOME` or `~/.cache`."""
    return _models_dev.cache_path(FILE)


def fetch_endpoints(
    fill: dict[str, str] = GAP_FILLERS,
    auth: dict[str, Auth] = AUTH_BY_PACKAGE,
    catalog: dict[str, Any] | None = None,
) -> Endpoints:
    """Build endpoints from models.dev (fetched unless `catalog` is given).
    URLs with a `${...}` placeholder are skipped."""
    providers: dict[str, Endpoint] = {}
    for provider_id, provider in (catalog or _models_dev.fetch_catalog()).items():
        api = provider.get("api")
        if not (isinstance(api, str) and api and "${" not in api):
            api = fill.get(provider_id)
        endpoint = Endpoint(base_url=api, auth=auth.get(provider.get("npm") or ""))
        if endpoint.base_url or endpoint.auth:
            providers[provider_id] = endpoint
    return Endpoints(fetched=datetime.now(UTC), providers=dict(sorted(providers.items())))


def save_endpoints(endpoints: Endpoints, path: Path | None = None) -> Path:
    """Write `endpoints` to `path`, or the cache file, and return the path."""
    return _models_dev.save(endpoints, path or default_cache_path())


def load_endpoints(path: Path | None = None, *, max_age: timedelta | None = None) -> Endpoints:
    """Load endpoints the way `avp.utils.pricing.load_prices` loads prices."""
    return _models_dev.load(
        Endpoints,
        path,
        default_path=default_cache_path(),
        bundled=bundled_endpoints,
        fetch=lambda: fetch_endpoints(),
        max_age=max_age,
    )


def default_base_url(endpoints: Endpoints, provider: str) -> str | None:
    """`provider`'s default `base_url`, or None."""
    endpoint = endpoints.providers.get(provider)
    return endpoint.base_url if endpoint else None


def provider_auth(endpoints: Endpoints, provider: str) -> Auth | None:
    """Where `provider`'s API key goes, or None when a proxy can't add it."""
    endpoint = endpoints.providers.get(provider)
    return endpoint.auth if endpoint else None
