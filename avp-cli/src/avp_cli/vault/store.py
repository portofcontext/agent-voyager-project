"""Secrets in the system's credential store, through `keyring`: the macOS
Keychain, Windows Credential Manager, or the Secret Service on Linux. Each is
stored under the service `avp` and its name. The store can't list its entries,
so each secret's name, description, and when it was last set, never its value, are also kept in
`~/.avp/secrets.json`."""

import re
from datetime import UTC, datetime

import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from pydantic import BaseModel, TypeAdapter

from avp_cli import paths
from avp_cli.console import Failed

SERVICE = "avp"
NAME = re.compile(r"[a-z0-9_-]+")
"""The pattern of a Commission's `{"proxy": NAME}`."""


class Secret(BaseModel):
    name: str
    updated: datetime
    """When the secret was last set."""
    description: str | None = None


SECRETS = TypeAdapter(list[Secret])


def check_name(name: str) -> None:
    if not NAME.fullmatch(name):
        raise Failed(
            f"{name!r} can't be a secret name: use lowercase letters, digits, '_', and '-'"
        )


def secrets() -> list[Secret]:
    try:
        return SECRETS.validate_json(paths.secrets().read_text())
    except FileNotFoundError:
        return []


def set_(name: str, value: str, description: str | None = None) -> None:
    """Without a description, a secret set again keeps the one it had."""
    try:
        keyring.set_password(SERVICE, name, value)
    except KeyringError as error:
        raise _unavailable(error) from None
    others = {secret.name: secret for secret in secrets()}
    previous = others.pop(name, None)
    if description is None and previous:
        description = previous.description
    secret = Secret(name=name, updated=datetime.now(UTC), description=description or None)
    _save([*others.values(), secret])


def stored(name: str) -> bool:
    """Whether the store still holds `name`, which it can lose outside avp. Reads
    the value."""
    try:
        return keyring.get_password(SERVICE, name) is not None
    except KeyringError as error:
        raise _unavailable(error) from None


def delete(name: str) -> None:
    """Fails when there is no secret named `name`."""
    remaining = [secret for secret in secrets() if secret.name != name]
    if len(remaining) == len(secrets()):
        raise Failed(f"no secret named {name!r}. `avp vault list` shows yours")
    try:
        keyring.delete_password(SERVICE, name)
    except PasswordDeleteError:
        pass  # Already removed from the store outside avp.
    except KeyringError as error:
        raise _unavailable(error) from None
    _save(remaining)


def _save(secrets: list[Secret]) -> None:
    paths.secrets().parent.mkdir(parents=True, exist_ok=True)
    paths.secrets().write_bytes(
        SECRETS.dump_json(sorted(secrets, key=lambda s: s.name), indent=2) + b"\n"
    )


def _unavailable(error: KeyringError) -> Failed:
    return Failed(
        f"the system's credential store failed ({error}). "
        "Without one, give the agent credentials with `avp run --env` or `--env-file`"
    )
