"""Each provider's default `base_url`, for a Model whose `base_url` is absent.

The Commission spec says an absent `base_url` means the service's default:
models.dev's `api` for the provider, or the URL the agent's client for that
service uses. An agent's client already knows its own endpoint; a supervisor
needs the URL itself, for sandbox egress, a credential proxy, or metering.

models.dev leaves out `api` for the providers whose clients have a URL built
in, such as `anthropic` and `openai`. `GAP_FILLERS` supplies those, with the
URL the provider's AI SDK client uses. models.dev's own `api` always wins.

Snapshots work as in `avp.utils.pricing`: one ships in
`avp/utils/data/avp_base_urls.json`, refreshed each time the package is
published, and `load_base_urls(max_age=...)` refreshes a cache file.
"""

from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from avp.utils import _models_dev
from avp.utils._models_dev import Snapshot

FILE = "avp_base_urls.json"

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


class BaseUrls(Snapshot):
    """Each provider's default `base_url`, as the cache file stores it."""

    providers: dict[str, str]
    """Keyed by models.dev's provider ID, the same as a Model's `provider`."""


@cache
def bundled_base_urls() -> BaseUrls:
    """The snapshot shipped in the package, as of its last publish."""
    return _models_dev.bundled(BaseUrls, FILE)


def default_cache_path() -> Path:
    """`$XDG_CACHE_HOME/avp/avp_base_urls.json`, or
    `~/.cache/avp/avp_base_urls.json` when `XDG_CACHE_HOME` isn't set."""
    return _models_dev.cache_path(FILE)


def fetch_base_urls(
    fill: dict[str, str] = GAP_FILLERS, catalog: dict[str, Any] | None = None
) -> BaseUrls:
    """Download models.dev and keep each provider's `api`, then add `fill` for
    the providers it leaves out. Skips URLs with a `${...}` placeholder, which
    need the caller's account. Needs network, unless `catalog` is models.dev's
    catalog already downloaded."""
    providers = dict(fill)
    for provider_id, provider in (catalog or _models_dev.fetch_catalog()).items():
        api = provider.get("api")
        if isinstance(api, str) and api and "${" not in api:
            providers[provider_id] = api
    return BaseUrls(fetched=datetime.now(UTC), providers=dict(sorted(providers.items())))


def save_base_urls(base_urls: BaseUrls, path: Path | None = None) -> Path:
    """Write `base_urls` to `path` (default: `default_cache_path()`) and return the path."""
    return _models_dev.save(base_urls, path or default_cache_path())


def load_base_urls(path: Path | None = None, *, max_age: timedelta | None = None) -> BaseUrls:
    """The base URLs to look up, chosen the way `avp.utils.pricing.load_prices`
    chooses prices: the newer of the cache file and the bundled snapshot, or
    the file at `path`, fetched again only when older than `max_age`."""
    return _models_dev.load(
        BaseUrls,
        path,
        default_path=default_cache_path(),
        bundled=bundled_base_urls,
        fetch=lambda: fetch_base_urls(),
        max_age=max_age,
    )


def default_base_url(base_urls: BaseUrls, provider: str) -> str | None:
    """The default `base_url` for `provider`, or None when it has none."""
    return base_urls.providers.get(provider)
