"""One sandbox per agent command: created, used, then deleted.

OpenSandbox starts each sandbox idle and runs commands in it through its exec
daemon, so avp fills the sandbox's vault before the agent starts and gets each
command's exit code and output."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from opensandbox.exceptions import SandboxException
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.sandboxes import Host, NetworkPolicy, NetworkRule, Volume
from opensandbox.sync.sandbox import SandboxSync

from avp_cli.console import Failed
from avp_cli.sandbox import service

LIFETIME = timedelta(minutes=10)
IO = "/io"
"""Where a run directory is mounted in the sandbox."""


@dataclass(frozen=True)
class Result:
    exit_code: int | None
    stdout: str
    stderr: str


@contextmanager
def sandbox(
    image: str, run_directory: Path | None = None, allowed_hosts: list[str] | None = None
) -> Generator[SandboxSync]:
    """A sandbox from the image, deleted on exit. It can reach only
    `allowed_hosts`: domains, `*.` wildcards, IP addresses, or CIDR ranges. A
    run directory is mounted at `IO`."""
    volumes = (
        [Volume(name="io", host=Host(path=str(run_directory)), mount_path=IO)]
        if run_directory
        else None
    )
    try:
        box = SandboxSync.create(
            image,
            timeout=LIFETIME,
            network_policy=NetworkPolicy(
                default_action="deny",
                egress=[NetworkRule(action="allow", target=h) for h in allowed_hosts or []],
            ),
            volumes=volumes,
            connection_config=service.connection(),
        )
    except SandboxException as exc:
        raise Failed(f"OpenSandbox couldn't start a sandbox from {image}: {exc}") from None
    try:
        yield box
    finally:
        box.kill()
        box.close()


def run(box: SandboxSync, command: list[str], env: dict[str, str] | None = None) -> Result:
    execution = box.commands.run(command, opts=RunCommandOpts(envs=env))
    return Result(
        exit_code=execution.exit_code,
        stdout="".join(m.text for m in execution.logs.stdout),
        stderr="".join(m.text for m in execution.logs.stderr),
    )
