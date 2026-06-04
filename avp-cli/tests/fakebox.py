"""A host-side stand-in for the OpenSandbox SDK used by the seam tests.

`FakeSandbox.create` mimics `SandboxSync.create`: it records the create kwargs
and returns a box whose `commands.run` executes the command on the HOST,
substituting each volume's mount path with its host path. The agent's run
contract, the NDJSON trajectory file, and run_agent's tail loop all stay real;
only the container boundary is simulated. Tests monkeypatch
`avp_cli.agent.SandboxSync` (and friends) with this class.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeLog:
    text: str  # mirrors the SDK's OutputMessage.text


@dataclass
class FakeLogs:
    stdout: list[FakeLog] = field(default_factory=list)
    stderr: list[FakeLog] = field(default_factory=list)


@dataclass
class FakeExecution:
    exit_code: int
    logs: FakeLogs = field(default_factory=FakeLogs)


class FakeCommands:
    def __init__(self, box: FakeSandbox) -> None:
        self._box = box

    def run(self, command: str, *, opts: Any = None, handlers: Any = None) -> FakeExecution:
        cmd = self._box.substitute(command)
        cwd = None
        if opts is not None and getattr(opts, "working_directory", None):
            cwd = self._box.substitute(opts.working_directory)
        env = {**os.environ, **{k: self._box.substitute(v) for k, v in self._box.env.items()}}
        timeout = None
        if opts is not None and getattr(opts, "timeout", None) is not None:
            timeout = opts.timeout.total_seconds()
        self._box.commands_run.append(cmd)
        try:
            r = subprocess.run(
                ["bash", "-c", cmd],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("command timed out") from exc
        return FakeExecution(
            exit_code=r.returncode,
            logs=FakeLogs(
                stdout=[FakeLog(r.stdout)] if r.stdout else [],
                stderr=[FakeLog(r.stderr)] if r.stderr else [],
            ),
        )


class FakeSandbox:
    """Drop-in for `SandboxSync` in tests. Class-level `created` records every
    create call's kwargs for assertion."""

    created: list[dict] = []

    def __init__(self, kwargs: dict) -> None:
        self.create_kwargs = kwargs
        self.env: dict[str, str] = kwargs.get("env") or {}
        self.mounts: dict[str, str] = {}
        for vol in kwargs.get("volumes") or []:
            self.mounts[vol.mount_path] = vol.host.path
        self.commands = FakeCommands(self)
        self.commands_run: list[str] = []
        self.killed = False

    @classmethod
    def create(cls, image: str, **kwargs: Any) -> FakeSandbox:
        box = cls({"image": image, **kwargs})
        cls.created.append(box.create_kwargs)
        return box

    def substitute(self, text: str) -> str:
        # Longest mount first so /avp/workspace wins over a hypothetical /avp.
        for mnt in sorted(self.mounts, key=len, reverse=True):
            text = text.replace(mnt, self.mounts[mnt])
        return text

    def kill(self) -> None:
        self.killed = True


def install(monkeypatch) -> type[FakeSandbox]:
    """Patch the SDK boundary in avp_cli.agent; returns the (reset) FakeSandbox."""
    from avp_cli import agent as agent_mod

    FakeSandbox.created = []
    monkeypatch.setattr(agent_mod, "SandboxSync", FakeSandbox)
    return FakeSandbox
