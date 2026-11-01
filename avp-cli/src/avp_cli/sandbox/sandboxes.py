"""One sandbox per agent command: created, used, then deleted.

OpenSandbox starts each sandbox idle and runs commands in it through its exec
daemon, so avp fills the sandbox's vault before the agent starts and gets each
command's exit code and output."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

from opensandbox.exceptions import SandboxException
from opensandbox.models.sandboxes import NetworkPolicy
from opensandbox.sync.sandbox import SandboxSync

from avp_cli.console import Failed
from avp_cli.sandbox import service

LIFETIME = timedelta(minutes=10)


@dataclass(frozen=True)
class Result:
    exit_code: int | None
    stdout: str
    stderr: str


@contextmanager
def sandbox(image: str) -> Generator[SandboxSync]:
    """A sandbox from the image, with no network, deleted on exit."""
    try:
        box = SandboxSync.create(
            image,
            timeout=LIFETIME,
            network_policy=NetworkPolicy(default_action="deny", egress=[]),
            connection_config=service.connection(),
        )
    except SandboxException as exc:
        raise Failed(f"OpenSandbox couldn't start a sandbox from {image}: {exc}") from None
    try:
        yield box
    finally:
        box.kill()
        box.close()


def run(box: SandboxSync, command: list[str]) -> Result:
    execution = box.commands.run(command)
    return Result(
        exit_code=execution.exit_code,
        stdout="".join(m.text for m in execution.logs.stdout),
        stderr="".join(m.text for m in execution.logs.stderr),
    )
