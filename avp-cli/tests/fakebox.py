"""A host-side stand-in for the sandbox runtime used by the seam tests.

`FakeRuntime.create` mimics a real backend: it records the create kwargs and
returns a box whose `run` executes the command on the HOST, substituting each
mount's target path with its host path. The agent's run contract, the NDJSON
trajectory file, and run_agent's tail loop all stay real; only the container
boundary is simulated. Tests monkeypatch `avp_cli.runtime.get_runtime` with this
(via `install`), so run_agent drives the fake exactly as it would a backend.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

from avp_cli.runtime import ExecResult, Mount


class FakeBox:
    def __init__(self, env: dict[str, str], mounts: list[Mount]) -> None:
        self.env = env or {}
        self.mounts: dict[str, str] = {m.target: m.host for m in mounts}
        self.commands_run: list[str] = []
        self.killed = False

    def substitute(self, text: str) -> str:
        # Longest mount first so /avp/workspace wins over a hypothetical /avp.
        for mnt in sorted(self.mounts, key=len, reverse=True):
            text = text.replace(mnt, self.mounts[mnt])
        return text

    def run(self, command: str, *, cwd: str | None = None, timeout_s: float) -> ExecResult:
        cmd = self.substitute(command)
        run_cwd = self.substitute(cwd) if cwd else None
        env = {**os.environ, **{k: self.substitute(v) for k, v in self.env.items()}}
        self.commands_run.append(cmd)
        try:
            r = subprocess.run(
                ["bash", "-c", cmd],
                cwd=run_cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("command timed out") from exc
        tail = "\n".join((r.stderr or r.stdout or "").strip().splitlines()[-3:])
        return ExecResult(exit_code=r.returncode, logs_tail=tail)

    def kill(self) -> None:
        self.killed = True


class FakeRuntime:
    """Drop-in for a runtime backend in tests. Class-level `created` records every
    create call's kwargs for assertion; `boxes` keeps the created FakeBoxes."""

    created: list[dict] = []
    boxes: list[FakeBox] = []

    def create(
        self,
        *,
        image: str,
        env: dict[str, str],
        mounts: list[Mount],
        egress: list[str],
        resources: dict[str, str],
        timeout_s: float,
        **extra: Any,
    ) -> FakeBox:
        FakeRuntime.created.append(
            {
                "image": image,
                "env": env,
                "mounts": mounts,
                "egress": egress,
                "resources": resources,
                "timeout_s": timeout_s,
            }
        )
        box = FakeBox(env, mounts)
        FakeRuntime.boxes.append(box)
        return box


def install(monkeypatch) -> type[FakeRuntime]:
    """Patch the runtime seam in avp_cli; returns the (reset) FakeRuntime."""
    from avp_cli import runtime as runtime_mod

    FakeRuntime.created = []
    FakeRuntime.boxes = []
    monkeypatch.setattr(runtime_mod, "get_runtime", lambda _name, _conn: FakeRuntime())
    return FakeRuntime
