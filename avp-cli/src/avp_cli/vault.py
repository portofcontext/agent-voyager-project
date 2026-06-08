"""Resolve SecretRef vault handles to secret values, supervisor-side.

A Commission carries credentials only as handles (`{"vault": "<name>"}`); the
real values live with the supervisor, never on the wire or in the trajectory.
This module is the supervisor's resolver.

Backends, first hit wins:
  1. host env var  `AVP_VAULT_<UPPER_SNAKE(handle)>`  (e.g. handle "openrouter"
     → `AVP_VAULT_OPENROUTER`); also the bare upper-cased handle as a fallback.
  2. `~/.avp/secrets.toml`, a `[secrets]` table keyed by handle.

PHASE 1 ("wire + env now"): the caller injects the resolved value into the
sandbox env / MCP headers, so the value does enter the sandbox. PHASE 2 will
move resolution behind a credential-injecting egress broker so the value never
enters the sandbox; this module's interface (handle in, value out) stays the
same, only the injection site changes.
"""

from __future__ import annotations

import tomllib

from avp_cli import paths

__all__ = ["VaultError", "resolve", "resolve_ref"]


class VaultError(Exception):
    """A vault handle could not be resolved from any backend."""


def _secrets_file() -> dict[str, str]:
    path = paths.avp_home() / "secrets.toml"
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text())
    table = data.get("secrets", data)
    return {k: str(v) for k, v in table.items() if isinstance(v, (str, int, float))}


def resolve(handle: str) -> str:
    """Resolve a vault handle to its secret value, or raise `VaultError`."""
    import os

    env_name = "AVP_VAULT_" + handle.upper().replace("-", "_")
    for candidate in (env_name, handle.upper().replace("-", "_")):
        val = os.environ.get(candidate)
        if val:
            return val
    file_val = _secrets_file().get(handle)
    if file_val:
        return file_val
    raise VaultError(
        f"vault handle {handle!r} not found. Set ${env_name} or add it under "
        f"[secrets] in {paths.avp_home() / 'secrets.toml'}."
    )


def resolve_ref(ref: object | None) -> str | None:
    """Resolve a `SecretRef`-shaped object (has `.vault`); None passes through."""
    if ref is None:
        return None
    return resolve(ref.vault)
