"""What pricing and base URLs share: fetching models.dev, and keeping a snapshot
of it in the package and in a cache file."""

import json
import os
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict

MODELS_DEV_API = "https://models.dev/api.json"


class Snapshot(BaseModel):
    """Data taken from models.dev at one time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = MODELS_DEV_API
    """Where the data came from."""
    fetched: AwareDatetime
    """When it was fetched."""


S = TypeVar("S", bound="Snapshot")


def fetch_catalog() -> dict[str, Any]:
    """models.dev's whole catalog, keyed by provider ID. Needs network."""
    # models.dev answers 403 to urllib's default User-Agent.
    request = urllib.request.Request(MODELS_DEV_API, headers={"User-Agent": "avp-python-sdk"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def bundled(kind: type[S], name: str) -> S:
    """The snapshot `name` shipped in the package, as of its last publish."""
    return kind.model_validate_json(resources.files("avp.utils").joinpath("data", name).read_text())


def cache_path(name: str) -> Path:
    """`$XDG_CACHE_HOME/avp/<name>`, or `~/.cache/avp/<name>` when
    `XDG_CACHE_HOME` isn't set."""
    root = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(root) / "avp" / name


def save(snapshot: Snapshot, path: Path) -> Path:
    """Write `snapshot` to `path` and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write a temporary file and rename it, so a reader never sees half a file.
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(snapshot.model_dump_json(indent=1, exclude_none=True) + "\n")
    partial.replace(path)
    return path


def load(
    kind: type[S],
    path: Path | None,
    *,
    default_path: Path,
    bundled: Callable[[], S],
    fetch: Callable[[], S],
    max_age: timedelta | None,
) -> S:
    """The newer of the cache file and the bundled snapshot when `path` is None,
    else the file at `path`; refreshed from models.dev when older than
    `max_age`. See `avp.utils.pricing.load_prices`."""
    file = path or default_path
    snapshot = kind.model_validate_json(file.read_text()) if file.exists() else None
    if path is None:
        shipped = bundled()
        if snapshot is None or shipped.fetched > snapshot.fetched:
            snapshot = shipped
    if max_age is not None and (snapshot is None or datetime.now(UTC) - snapshot.fetched > max_age):
        snapshot = fetch()
        save(snapshot, file)
    if snapshot is None:
        raise FileNotFoundError(file)
    return snapshot
