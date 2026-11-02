"""The agent's environment: only the variables given with `--env` and
`--env-file`, checked against the `env` Secret references in the Commission."""

import os
from pathlib import Path

from dotenv import dotenv_values

from avp.commission import Commission, EnvSecret, McpServerHttp
from avp_cli.console import Failed


def variables(env: list[str], env_files: list[Path]) -> dict[str, str]:
    """`--env-file` files, then `--env` values, later ones winning. A file is
    read as python-dotenv reads it (quotes removed, `export` allowed), without
    `${VAR}` expansion, so a value never comes from avp's own environment. In
    `--env`, as with Docker, `NAME=VALUE` sets a value and `NAME` copies it
    from avp's own environment."""
    result: dict[str, str] = {}
    for path in env_files:
        for name, value in dotenv_values(path, interpolate=False).items():
            if value is None:
                raise Failed(f"{path} names {name} without a value; write {name}=VALUE")
            result[name] = value
    for item in env:
        name, sep, value = item.partition("=")
        if not sep:
            if name not in os.environ:
                raise Failed(f"--env {name} copies {name}, which isn't set here")
            value = os.environ[name]
        result[name] = value
    return result


def references(commission: Commission) -> dict[str, str]:
    """Each variable an `env` Secret reference names, with where it is."""
    found: dict[str, str] = {}
    if isinstance(commission.model.credential, EnvSecret):
        found[commission.model.credential.env] = "model.credential"
    for server in commission.mcp_servers or []:
        values = server.headers if isinstance(server, McpServerHttp) else server.env
        for key, value in (values or {}).items():
            if isinstance(value, EnvSecret):
                found.setdefault(value.env, f"MCP server {server.id!r}, {key}")
    return found


def check(commission: Commission, given: dict[str, str]) -> None:
    """Fail before the run when a variable the Commission refers to wasn't given."""
    missing = {name: where for name, where in references(commission).items() if name not in given}
    if missing:
        listed = ", ".join(f"{name} ({where})" for name, where in missing.items())
        raise Failed(f"the Commission reads {listed}; pass it with --env or --env-file")
