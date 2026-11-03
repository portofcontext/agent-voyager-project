"""Each provider's default `base_url` and the header its API key goes in, for
sandbox egress, metering, or a credential proxy.

URLs come from models.dev's `api`, with `GAP_FILLERS` for providers it omits.
Auth comes from the provider's `npm` package via `AUTH_BY_PACKAGE`. Snapshots
work as in `avp.utils.pricing`.
"""

import json
from datetime import UTC, datetime, timedelta
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from avp.utils import _models_dev
from avp.utils._models_dev import Snapshot

FILE = "avp_endpoints.json"

_DEFAULTS = json.loads(
    resources.files("avp.utils").joinpath("data", "avp_endpoint_defaults.json").read_text()
)

GAP_FILLERS: dict[str, str] = _DEFAULTS["gap_fillers"]
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
    package: Auth.model_validate(auth) for package, auth in _DEFAULTS["auth_by_package"].items()
}
"""Packages whose key is a fixed header value. Others, such as
`@ai-sdk/google-vertex`, are left out. Bedrock supports API keys only here,
not SigV4."""


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
