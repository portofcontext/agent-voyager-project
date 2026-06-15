"""The sandbox-runtime seam: create a sandbox from an image, run commands in it,
tear it down. Everything else in `agent.run_agent` (building the env, deriving the
egress allowlist, seeding the io dir, tailing the trajectory file through the io
bind mount) is runtime-agnostic, so the backends only have to provide three
operations: create, run, kill.

Two backends:

- `opensandbox` (default): the managed OpenSandbox control-plane server. Full
  isolation with a DNS-filtering egress sidecar; the production path today.
- `libkrun`: a podman machine on the libkrun provider. Its reason to exist is GPU
  passthrough — on Apple Silicon it exposes the host GPU to the Linux guest via
  virtio-gpu Venus, so an in-process local model (goose's `local` provider) runs
  GPU-accelerated. Selected with `AVP_RUNTIME=libkrun`.

The selection is a deliberate seam for the planned move off OpenSandbox; see the
coupling map in the design notes. The interface is intentionally minimal so a
third backend (e.g. OpenShell) drops in behind the same `Box`.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol


@dataclass(frozen=True)
class Mount:
    """A host directory bound into the sandbox (read-write)."""

    host: str
    target: str


@dataclass(frozen=True)
class ExecResult:
    """The outcome of one command in the sandbox. `exit_code` is None when the
    backend can't report one (treated as success, matching OpenSandbox)."""

    exit_code: int | None
    logs_tail: str = ""


class Box(Protocol):
    """A live sandbox. `run` executes one command to completion; `kill` tears it
    down (always called, even on error)."""

    def run(self, command: str, *, cwd: str | None = None, timeout_s: float) -> ExecResult: ...

    def kill(self) -> None: ...


# ── OpenSandbox backend ──────────────────────────────────────────────────────


class OpenSandboxBox:
    """Wraps an OpenSandbox `SandboxSync`. Faithful to the prior inline calls so
    the existing docker-seam behavior is unchanged."""

    def __init__(self, box: object) -> None:
        self._box = box

    def run(self, command: str, *, cwd: str | None = None, timeout_s: float) -> ExecResult:
        from opensandbox.models.execd import RunCommandOpts

        opts = RunCommandOpts(working_directory=cwd, timeout=timedelta(seconds=timeout_s))
        execution = self._box.commands.run(command, opts=opts)
        chunks = [log.text for log in (execution.logs.stderr or execution.logs.stdout or [])]
        tail = "\n".join("".join(chunks).strip().splitlines()[-3:])
        return ExecResult(exit_code=execution.exit_code, logs_tail=tail)

    def kill(self) -> None:
        self._box.kill()


@dataclass
class OpenSandboxRuntime:
    """Creates sandboxes on the managed OpenSandbox server."""

    connection_config: object  # ConnectionConfigSync

    def create(
        self,
        *,
        image: str,
        env: dict[str, str],
        mounts: list[Mount],
        egress: list[str],
        resources: dict[str, str],
        timeout_s: float,
    ) -> OpenSandboxBox:
        from opensandbox import SandboxSync
        from opensandbox.models.sandboxes import Host, Volume

        from avp_cli import osb

        volumes = [
            Volume(name=f"m{i}", host=Host(path=m.host), mount_path=m.target)
            for i, m in enumerate(mounts)
        ]
        box = SandboxSync.create(
            image,
            connection_config=self.connection_config,
            env=env,
            volumes=volumes,
            network_policy=osb.network_policy(egress),
            resource=resources,
            timeout=timedelta(seconds=timeout_s),
        )
        return OpenSandboxBox(box)


# ── libkrun backend (podman, GPU-capable) ────────────────────────────────────

# The libkrun podman machine that exposes the GPU (virtio-gpu Venus). Created out
# of band (`podman machine init` under CONTAINERS_MACHINE_PROVIDER=libkrun); this
# backend assumes it exists and is running.
LIBKRUN_MACHINE = os.environ.get("AVP_LIBKRUN_MACHINE", "krunkit-gpu")
# The guest GPU device to pass through; renderD128 is the world-accessible Venus
# render node (card0 is root-only). "none" disables passthrough.
LIBKRUN_GPU_DEVICE = os.environ.get("AVP_LIBKRUN_GPU_DEVICE", "/dev/dri")


def _podman_env() -> dict[str, str]:
    env = dict(os.environ)
    env["CONTAINERS_MACHINE_PROVIDER"] = "libkrun"
    return env


class LibkrunBox:
    """A podman container on the libkrun machine. `run` is `podman exec`."""

    def __init__(self, name: str, penv: dict[str, str]) -> None:
        self._name = name
        self._env = penv

    def run(self, command: str, *, cwd: str | None = None, timeout_s: float) -> ExecResult:
        argv = ["podman", "exec"]
        if cwd:
            argv += ["-w", cwd]
        argv += [self._name, "sh", "-c", command]
        try:
            proc = subprocess.run(
                argv,
                env=self._env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(exit_code=124, logs_tail=f"timed out after {timeout_s:.0f}s")
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-3:])
        return ExecResult(exit_code=proc.returncode, logs_tail=tail)

    def kill(self) -> None:
        subprocess.run(
            ["podman", "rm", "-f", self._name],
            env=self._env,
            capture_output=True,
            text=True,
        )


@dataclass
class LibkrunRuntime:
    """Creates GPU-capable containers on the libkrun podman machine.

    Egress: local-inference runs need no network (the model is mounted), so the
    container is created with `--network none` by default — stronger than the
    OpenSandbox default and enough for the GPU local-model path. Commissions that
    need egress (hosted providers, MCP) are the remaining parity gap with
    OpenSandbox's DNS-filtering sidecar; see the design notes.
    """

    counter: int = field(default=0)

    def create(
        self,
        *,
        image: str,
        env: dict[str, str],
        mounts: list[Mount],
        egress: list[str],
        resources: dict[str, str],
        timeout_s: float,
    ) -> LibkrunBox:
        penv = _podman_env()
        self.counter += 1
        name = f"avp-{os.getpid()}-{self.counter}"
        argv = ["podman", "run", "-d", "--name", name]
        if LIBKRUN_GPU_DEVICE and LIBKRUN_GPU_DEVICE != "none":
            argv += ["--device", LIBKRUN_GPU_DEVICE]
        # Local inference needs no egress; deny by default. (Egress parity for
        # networked commissions is a follow-up.)
        argv += ["--network", "none" if not egress else "bridge"]
        if resources.get("cpu"):
            argv += ["--cpus", str(resources["cpu"])]
        if resources.get("memory"):
            argv += ["--memory", str(resources["memory"]).replace("Gi", "g").replace("Mi", "m")]
        for k, v in env.items():
            argv += ["-e", f"{k}={v}"]
        for m in mounts:
            argv += ["-v", f"{m.host}:{m.target}"]
        # Keep the container alive so we can exec setup + the agent into it.
        argv += ["--entrypoint", "sh", image, "-c", "sleep infinity"]
        proc = subprocess.run(argv, env=penv, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"podman run failed: {proc.stderr.strip()[-400:]}")
        return LibkrunBox(name, penv)


RUNTIMES = ("opensandbox", "libkrun")


def resolve_runtime_name(cli_value: str | None) -> str:
    """The backend name: the explicit CLI `--runtime` wins, else the `AVP_RUNTIME`
    env (a documented fallback for CI and any path without the flag), else the
    default `opensandbox`."""
    return cli_value or os.environ.get("AVP_RUNTIME") or "opensandbox"


def get_runtime(name: str, connection_config: object) -> OpenSandboxRuntime | LibkrunRuntime:
    """Construct the named backend. `connection_config` is used only by the
    OpenSandbox backend (the libkrun backend talks to a podman machine)."""
    if name == "libkrun":
        return LibkrunRuntime()
    return OpenSandboxRuntime(connection_config=connection_config)
