"""Launcher utilities, outside the AVP wire contract.

Launchers own workspace, native SDK state, credentials, and cleanup. Adapters
inherit that context. These helpers give the CLI and conformance runner the
same directory policy without putting deployment policy in each adapter.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path


def directory_env(root: Path, workspace: Path | None = None) -> dict[str, str]:
    """Directory defaults for any adapter, on the host or inside a container.

    Pure mapping: paths belong to the target filesystem; no directories are
    created here. Explicit launcher configuration may override these defaults.
    """
    home = root / "home"
    return {
        "AVP_ENV_ROOT": str(root),
        "AVP_WORKSPACE": str(workspace if workspace is not None else root / "workspace"),
        "HOME": str(home),
        "USERPROFILE": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "CODEX_HOME": str(root / "state/codex"),
        "CODEX_SQLITE_HOME": str(root / "state/codex"),
        "CLAUDE_CONFIG_DIR": str(root / "state/claude"),
        "GOOSE_PATH_ROOT": str(root / "state/goose"),
    }


@contextmanager
def local_environment(overrides: Mapping[str, str]) -> Iterator[dict[str, str]]:
    """Fresh state for one host subprocess; explicit manifest env wins.

    Credentials and other host environment variables pass through. This is
    state separation, not an OS sandbox. Build tool caches stay on the host so
    source manifests can still bootstrap uv/cargo before entering the workspace.
    Only the owned temporary root is deleted, including on spawn/run failure.
    """
    env = dict(os.environ)
    host_home = Path.home()
    env.setdefault("CARGO_HOME", str(host_home / ".cargo"))
    env.setdefault("RUSTUP_HOME", str(host_home / ".rustup"))
    cache = (
        host_home / "Library/Caches"
        if sys.platform == "darwin"
        else Path(env.get("XDG_CACHE_HOME", str(host_home / ".cache")))
    )
    env.setdefault("UV_CACHE_DIR", str(cache / "uv"))
    with tempfile.TemporaryDirectory(prefix="avp-launch-") as tmp:
        defaults = directory_env(Path(tmp).resolve())
        env.update(defaults)
        env.update(overrides)
        for name in defaults:
            Path(env[name]).mkdir(parents=True, exist_ok=True)
        yield env
