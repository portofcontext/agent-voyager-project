"""Secrets in the system's credential store, through `keyring`: the macOS
Keychain, Windows Credential Manager, or the Secret Service on Linux. Each is
stored under the service `avp` and its name. The store can't list its entries,
so each secret's name, description, when it was last set, and for an OAuth
sign-in where the token comes from and when it expires, never its value, are
also kept in `~/.avp/vault.json`."""

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


class OAuth(BaseModel):
    """Where an OAuth sign-in's token comes from, and when it expires."""

    url: str
    """The MCP server signed in to."""
    token_endpoint: str
    resource: str | None = None
    """The RFC 8707 resource a token is requested for, when the server names one."""
    scopes: list[str] = []
    expires_at: datetime | None = None
    """None when the server didn't say."""


class Secret(BaseModel):
    name: str
    updated: datetime
    """When the secret was last set."""
    description: str | None = None
    oauth: OAuth | None = None


SECRETS = TypeAdapter(list[Secret])


def check_name(name: str) -> None:
    if not NAME.fullmatch(name):
        raise Failed(
            f"{name!r} can't be a secret name: use lowercase letters, digits, '_', and '-'"
        )


def secrets() -> list[Secret]:
    try:
        return SECRETS.validate_json(paths.vault().read_text())
    except FileNotFoundError:
        return []


def find(name: str) -> Secret:
    for secret in secrets():
        if secret.name == name:
            return secret
    raise Failed(f"no secret named {name!r}. `avp vault list` shows yours")


def get(name: str) -> str:
    """The secret's value. Fails when the store doesn't hold it."""
    try:
        value = keyring.get_password(SERVICE, name)
    except KeyringError as error:
        raise _unavailable(error) from None
    if value is None:
        raise Failed(f"the credential store doesn't hold {name!r}. Set it again, or delete it")
    return value


def set_(name: str, value: str, description: str | None = None, oauth: OAuth | None = None) -> None:
    """Without a description, a secret set again keeps the one it had."""
    try:
        keyring.set_password(SERVICE, name, value)
    except KeyringError as error:
        raise _unavailable(error) from None
    others = {secret.name: secret for secret in secrets()}
    previous = others.pop(name, None)
    if description is None and previous:
        description = previous.description
    secret = Secret(
        name=name, updated=datetime.now(UTC), description=description or None, oauth=oauth
    )
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
    find(name)
    try:
        keyring.delete_password(SERVICE, name)
    except PasswordDeleteError:
        pass  # Already removed from the store outside avp.
    except KeyringError as error:
        raise _unavailable(error) from None
    _save([secret for secret in secrets() if secret.name != name])


def _save(secrets: list[Secret]) -> None:
    paths.vault().parent.mkdir(parents=True, exist_ok=True)
    paths.vault().write_bytes(
        SECRETS.dump_json(sorted(secrets, key=lambda s: s.name), indent=2) + b"\n"
    )


def _unavailable(error: KeyringError) -> Failed:
    return Failed(
        f"the system's credential store failed ({error}). "
        "Without one, give the agent credentials with `avp run --env` or `--env-file`"
    )
