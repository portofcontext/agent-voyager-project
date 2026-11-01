"""Each provider's default `base_url`, and where its API key goes in a request.

A supervisor needs both for a Model, though the agent's client already knows
them: the URL for sandbox egress, a credential proxy, or metering, and the
key's header for a credential proxy, which adds the key to the agent's requests
the way the provider's API expects.

The Commission spec says an absent `base_url` means the service's default:
models.dev's `api` for the provider, or the URL the agent's client for that
service uses. models.dev leaves out `api` for the providers whose clients have
a URL built in, such as `anthropic` and `openai`. `GAP_FILLERS` supplies those,
with the URL the provider's AI SDK client uses. models.dev's own `api` always
wins.

The key's header comes from the AI SDK package models.dev names for each
provider (`npm`), since the package decides how a request authenticates.
`AUTH_BY_PACKAGE` maps each package whose header is known; a provider whose
package isn't there has no `auth`.

Snapshots work as in `avp.utils.pricing`: one ships in
`avp/utils/data/avp_endpoints.json`, refreshed each time the package is
published, and `load_endpoints(max_age=...)` refreshes a cache file.
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
"""Providers models.dev gives no `api`, and the URL their AI SDK client uses.
Providers whose URL depends on the account or region, such as
`amazon-bedrock`, `azure`, and `google-vertex`, have no default."""


class Auth(BaseModel):
    """Where a provider's API key goes in a request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    header: str
    """The request header that carries the key, in lowercase."""
    prefix: str = ""
    """What comes before the key in the header's value, such as `"Bearer "`."""


BEARER = Auth(header="authorization", prefix="Bearer ")

AUTH_BY_PACKAGE: dict[str, Auth] = {
    "@ai-sdk/anthropic": Auth(header="x-api-key"),
    "@ai-sdk/azure": Auth(header="api-key"),
    "@ai-sdk/google": Auth(header="x-goog-api-key"),
    # Bedrock API keys. Signed AWS credentials can't go through a proxy.
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
"""Each AI SDK package whose API key travels in a fixed header. Packages that
authenticate another way, such as `@ai-sdk/google-vertex` with short-lived
OAuth tokens, are left out."""


class Endpoint(BaseModel):
    """One provider's defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str | None = None
    """The default `base_url`, or None when it depends on the account or region."""
    auth: Auth | None = None
    """Where the API key goes, or None when the key isn't a fixed header value
    or the header isn't known. A credential proxy can't add such a key."""


class Endpoints(Snapshot):
    """Each provider's defaults, as the cache file stores it."""

    providers: dict[str, Endpoint]
    """Keyed by models.dev's provider ID, the same as a Model's `provider`."""


@cache
def bundled_endpoints() -> Endpoints:
    """The snapshot shipped in the package, as of its last publish."""
    return _models_dev.bundled(Endpoints, FILE)


def default_cache_path() -> Path:
    """`$XDG_CACHE_HOME/avp/avp_endpoints.json`, or
    `~/.cache/avp/avp_endpoints.json` when `XDG_CACHE_HOME` isn't set."""
    return _models_dev.cache_path(FILE)


def fetch_endpoints(
    fill: dict[str, str] = GAP_FILLERS,
    auth: dict[str, Auth] = AUTH_BY_PACKAGE,
    catalog: dict[str, Any] | None = None,
) -> Endpoints:
    """Download models.dev and keep each provider's `api`, with `fill` for the
    providers it leaves out, and the `auth` for its `npm` package. Skips URLs
    with a `${...}` placeholder, which need the caller's account, and providers
    with neither a URL nor an auth. Needs network, unless `catalog` is
    models.dev's catalog already downloaded."""
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
    """Write `endpoints` to `path` (default: `default_cache_path()`) and return the path."""
    return _models_dev.save(endpoints, path or default_cache_path())


def load_endpoints(path: Path | None = None, *, max_age: timedelta | None = None) -> Endpoints:
    """The endpoints to look up, chosen the way `avp.utils.pricing.load_prices`
    chooses prices: the newer of the cache file and the bundled snapshot, or
    the file at `path`, fetched again only when older than `max_age`."""
    return _models_dev.load(
        Endpoints,
        path,
        default_path=default_cache_path(),
        bundled=bundled_endpoints,
        fetch=lambda: fetch_endpoints(),
        max_age=max_age,
    )


def default_base_url(endpoints: Endpoints, provider: str) -> str | None:
    """The default `base_url` for `provider`, or None when it has none."""
    endpoint = endpoints.providers.get(provider)
    return endpoint.base_url if endpoint else None


def provider_auth(endpoints: Endpoints, provider: str) -> Auth | None:
    """Where `provider`'s API key goes in a request, or None when a credential
    proxy can't add it: the key isn't a fixed header value, or the provider or
    its header isn't known."""
    endpoint = endpoints.providers.get(provider)
    return endpoint.auth if endpoint else None
