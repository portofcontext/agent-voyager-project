"""One sandbox per agent command: created, used, then deleted.

OpenSandbox starts each sandbox idle and runs commands in it through its exec
daemon, so avp fills the sandbox's vault before the agent starts and gets each
command's exit code and output."""

import shlex
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from opensandbox.exceptions import SandboxException
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.sandboxes import (
    Credential,
    CredentialBinding,
    CredentialProxyConfig,
    Host,
    NetworkPolicy,
    NetworkRule,
    Volume,
)
from opensandbox.sync.sandbox import SandboxSync

from avp_cli.console import Failed, detail
from avp_cli.sandbox import service

LIFETIME = timedelta(minutes=10)
IO = "/io"
"""Where a run directory is mounted in the sandbox."""


@dataclass(frozen=True)
class Vault:
    """What a sandbox's Credential Vault holds: credentials, and the bindings
    that say which requests each is added to."""

    credentials: list[Credential]
    bindings: list[CredentialBinding]


@dataclass(frozen=True)
class Result:
    exit_code: int | None
    stdout: str
    stderr: str


@contextmanager
def sandbox(
    image: str,
    run_directory: Path | None = None,
    allowed_hosts: list[str] | None = None,
    volumes: list[Volume] | None = None,
    vault: Vault | None = None,
) -> Generator[SandboxSync]:
    """A sandbox from the image, deleted on exit. It can reach only
    `allowed_hosts`: domains, `*.` wildcards, IP addresses, or CIDR ranges. A
    run directory is mounted at `IO`, and each of `volumes` where it says. With
    `vault`, its Credential Vault is filled before anything runs in it."""
    if run_directory:
        io = Volume(name="io", host=Host(path=str(run_directory)), mount_path=IO)
        volumes = [io, *(volumes or [])]
    try:
        box = SandboxSync.create(
            image,
            timeout=LIFETIME,
            network_policy=NetworkPolicy(
                default_action="deny",
                egress=[NetworkRule(action="allow", target=h) for h in allowed_hosts or []],
            ),
            volumes=volumes,
            credential_proxy=CredentialProxyConfig(enabled=True) if vault else None,
            connection_config=service.connection(),
        )
    except SandboxException as exc:
        hint = ""
        if "dns+nft" in str(exc):
            hint = ". The service started before avp needed it; restart it with `avp sandbox stop`"
        raise Failed(f"OpenSandbox couldn't start a sandbox from {image}: {exc}{hint}") from None
    try:
        if vault:
            try:
                box.credential_vault.create(
                    credentials=[*vault.credentials], bindings=[*vault.bindings]
                )
            except SandboxException as exc:
                raise Failed(f"OpenSandbox couldn't fill the sandbox's vault: {exc}") from None
        yield box
    finally:
        box.kill()
        box.close()


def run(box: SandboxSync, command: list[str], env: dict[str, str] | None = None) -> Result:
    """Run the command and wait for it. Details name `env`'s variables, not their values."""
    detail(f"Running {shlex.join(command)}")
    if env:
        detail(f"With the variables {', '.join(sorted(env))}")
    execution = box.commands.run(command, opts=RunCommandOpts(envs=env))
    detail(f"Exited with {execution.exit_code}")
    return Result(
        exit_code=execution.exit_code,
        stdout="".join(m.text for m in execution.logs.stdout),
        stderr="".join(m.text for m in execution.logs.stderr),
    )
