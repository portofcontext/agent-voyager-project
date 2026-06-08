"""Resolve SecretRef vault handles to secret values, supervisor-side.

A Commission carries credentials only as handles (`{"vault": "<name>"}`); the
real values live with the supervisor, never on the wire or in the trajectory.
This module is the supervisor's resolver.

Backends, first hit wins:
  1. host env var  `AVP_VAULT_<UPPER_SNAKE(handle)>`  (e.g. handle "openrouter"
     → `AVP_VAULT_OPENROUTER`); also the bare upper-cased handle as a fallback.
  2. `~/.avp/secrets.toml`, a `[secrets]` table keyed by handle.

The resolved value is handed to the credential-injecting broker
(`avp_cli.broker`), which holds it on the host and injects it into outbound
requests. It is never written into the sandbox, so the agent uses the
credential without being able to read it.
"""

from __future__ import annotations

import re
import tomllib

from avp_cli import paths

__all__ = ["VaultError", "names", "remove", "resolve", "resolve_ref", "secrets_path", "store"]

# A vault handle matches the SecretRef wire pattern (avp.commission._ID_PATTERN).
_HANDLE_RE = re.compile(r"^[a-z0-9_-]+$")


class VaultError(Exception):
    """A vault handle could not be resolved, or a handle/value was invalid."""


def secrets_path():
    """Path to the on-disk secrets file (a `[secrets]` TOML table)."""
    return paths.avp_home() / "secrets.toml"


def _secrets_file() -> dict[str, str]:
    path = secrets_path()
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text())
    table = data.get("secrets", data)
    return {k: str(v) for k, v in table.items() if isinstance(v, (str, int, float))}


def _validate_handle(handle: str) -> None:
    if not _HANDLE_RE.match(handle):
        raise VaultError(
            f"invalid handle {handle!r}: use lowercase letters, digits, '-', '_' "
            "(the SecretRef vault pattern a Commission references)"
        )


def _write_secrets(table: dict[str, str]) -> None:
    """Write the secrets table to disk, mode 0600 (the file holds plaintext)."""
    lines = ["# avp vault secrets. Referenced by handle in Commissions", "[secrets]"]
    for handle in sorted(table):
        escaped = table[handle].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{handle} = "{escaped}"')
    path = secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


def names() -> list[str]:
    """Handle names in the on-disk vault (never the values)."""
    return sorted(_secrets_file())


def store(handle: str, value: str) -> None:
    """Store (or replace) a secret under `handle` in the on-disk vault."""
    _validate_handle(handle)
    if not value:
        raise VaultError("refusing to store an empty value")
    table = _secrets_file()
    table[handle] = value
    _write_secrets(table)


def remove(handle: str) -> bool:
    """Delete a handle from the on-disk vault; True if it was present."""
    table = _secrets_file()
    if handle not in table:
        return False
    del table[handle]
    _write_secrets(table)
    return True


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
