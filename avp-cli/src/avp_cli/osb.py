"""The sandbox engine: a CLI-managed local OpenSandbox control plane.

Every agent run happens inside a container. `avp` owns the whole stack so the
user-visible prerequisite is exactly one thing: a reachable Docker daemon.
The OpenSandbox server (`opensandbox-server`, a FastAPI control plane over
Docker) is a pinned dependency of this package; `ensure_server()` generates its
config under `~/.avp/opensandbox/` on first use, spawns it detached, and reuses
a healthy instance across invocations. Call sites then drive sandboxes through
the `opensandbox` SDK with the returned connection.

Policy posture carries over from the srt era with the boundary moved: the
container replaces the write-allowlist (the host filesystem simply isn't
there), bind mounts are restricted to `~/.avp` via the server's
`allowed_host_paths`, and the network stays an explicit egress allowlist
(default-deny + the model-provider domains below + the env's `net`).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from opensandbox.config import ConnectionConfigSync
from opensandbox.models.sandboxes import NetworkPolicy, NetworkRule

from avp_cli import paths

# The egress allow-list every sandbox starts from. Seeded with the major
# model-provider APIs (the agent calls whatever the commission's model resolves
# to) plus GitHub; an env's `net` domains are added per run. Default action is
# deny, so anything not listed is unreachable.
DEFAULT_ALLOW_DOMAINS: tuple[str, ...] = (
    "api.anthropic.com",
    "*.anthropic.com",
    "api.openai.com",
    "*.openai.com",
    "generativelanguage.googleapis.com",
    "*.googleapis.com",
    "api.mistral.ai",
    "openrouter.ai",
    "github.com",
    "*.githubusercontent.com",
)

# Not 8080: the OpenSandbox default collides with half the dev tools in the
# world; this server exists only for avp and hides behind this module.
DEFAULT_PORT = 18763

_HEALTH_TIMEOUT_S = 20.0  # max wait for a freshly spawned server to come up
_HEALTH_POLL_S = 0.25


class SandboxUnavailable(Exception):
    """The sandbox stack can't run here (no Docker, server failed to start)."""


@dataclass(frozen=True)
class Connection:
    """How to reach the managed server; feeds the SDK's ConnectionConfigSync."""

    domain: str  # host:port
    api_key: str

    def config(self) -> ConnectionConfigSync:
        return ConnectionConfigSync(domain=self.domain, api_key=self.api_key, protocol="http")


def server_dir() -> Path:
    """Where the managed server keeps its config, db, log, and pidfile."""
    return paths.avp_home() / "opensandbox"


def docker_available() -> str | None:
    """None if the Docker daemon is reachable, else a one-line diagnosis."""
    docker = shutil.which("docker")
    if docker is None:
        return (
            "Docker is not installed. Agent runs execute in containers; install "
            "Docker Desktop, OrbStack, or colima and retry."
        )
    try:
        probe = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return "Docker is not responding (`docker info` timed out). Is the daemon starting up?"
    if probe.returncode != 0:
        return (
            "the Docker daemon is not running. Start Docker Desktop / "
            "`colima start` and retry."
        )
    return None


def ensure_server() -> Connection:
    """Bring up (or reuse) the managed OpenSandbox server; return its connection.

    Idempotent: a healthy server on the configured port is reused as-is. The
    config TOML is generated once and then owned by the user (edits persist);
    the API key lives in it, minted on first run, file mode 0600.

    Raises `SandboxUnavailable` with an actionable message when Docker is
    missing or the server fails to come up (log tail included).
    """
    diagnosis = docker_available()
    if diagnosis is not None:
        raise SandboxUnavailable(diagnosis)

    conn = _connection_from_config(_ensure_config())
    if _healthy(conn.domain):
        return conn
    _spawn_server()
    deadline = time.monotonic() + _HEALTH_TIMEOUT_S
    while time.monotonic() < deadline:
        if _healthy(conn.domain):
            return conn
        time.sleep(_HEALTH_POLL_S)
    raise SandboxUnavailable(
        "the sandbox server did not become healthy within "
        f"{_HEALTH_TIMEOUT_S:.0f}s. Log tail ({_log_path()}):\n{_log_tail()}"
    )


def network_policy(extra_domains: list[str] | None = None) -> NetworkPolicy:
    """Default-deny egress policy: provider domains + any env `net` additions."""
    domains = list(dict.fromkeys([*DEFAULT_ALLOW_DOMAINS, *(extra_domains or [])]))
    return NetworkPolicy(
        default_action="deny",
        egress=[NetworkRule(action="allow", target=d) for d in domains],
    )


def server_status() -> dict:
    """A small status snapshot for `avp sandbox status`."""
    cfg_path = server_dir() / "config.toml"
    status: dict = {"config": str(cfg_path), "configured": cfg_path.is_file()}
    status["docker"] = docker_available() or "ok"
    if cfg_path.is_file():
        conn = _connection_from_config(cfg_path)
        status["domain"] = conn.domain
        status["healthy"] = _healthy(conn.domain)
        if status["healthy"]:
            status["sandboxes"] = _sandbox_count(conn)
    return status


def stop_server() -> bool:
    """Stop the managed server if our pidfile points at a live process."""
    pid_path = server_dir() / "server.pid"
    if not pid_path.is_file():
        return False
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 15)
    except (ValueError, ProcessLookupError, PermissionError):
        pid_path.unlink(missing_ok=True)
        return False
    pid_path.unlink(missing_ok=True)
    return True


# ── internals ─────────────────────────────────────────────────────────────────


def _ensure_config() -> Path:
    """Write the server config on first use; afterwards the user owns the file."""
    d = server_dir()
    cfg = d / "config.toml"
    if cfg.is_file():
        return cfg
    d.mkdir(parents=True, exist_ok=True)
    api_key = secrets.token_hex(32)
    # Keys mirror the packaged docker example config of the pinned
    # opensandbox-server; only the avp-specific values differ. Bind mounts are
    # restricted to ~/.avp: run workspaces live there and nothing else on the
    # host is mountable into a sandbox.
    cfg.write_text(
        f"""\
# Generated by avp on first sandbox use. Edits persist; delete to regenerate.
[server]
host = "127.0.0.1"
port = {DEFAULT_PORT}
api_key = "{api_key}"
max_sandbox_timeout_seconds = 86400

[log]
level = "INFO"

[runtime]
type = "docker"
execd_image = "opensandbox/execd:v1.0.16"

[storage]
allowed_host_paths = ["{paths.avp_home()}"]

[store]
type = "sqlite"
path = "{d / "state.db"}"

[docker]
network_mode = "bridge"
no_new_privileges = true
pids_limit = 4096

[ingress]
mode = "direct"

[egress]
image = "opensandbox/egress:v1.0.12"
mode = "dns"
"""
    )
    cfg.chmod(0o600)
    return cfg


def _connection_from_config(cfg_path: Path) -> Connection:
    cfg = tomllib.loads(cfg_path.read_text())
    server = cfg.get("server", {})
    host = server.get("host", "127.0.0.1")
    port = server.get("port", DEFAULT_PORT)
    api_key = server.get("api_key", "")
    return Connection(domain=f"{host}:{port}", api_key=api_key)


def _spawn_server() -> None:
    """Launch the server detached, logging to the server dir, pidfile recorded."""
    log_path = _log_path()
    with log_path.open("ab") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "opensandbox_server.cli", "--config",
             str(server_dir() / "config.toml")],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # survives this CLI invocation
        )
    (server_dir() / "server.pid").write_text(str(proc.pid))


def _log_path() -> Path:
    return server_dir() / "server.log"


def _log_tail(lines: int = 10) -> str:
    try:
        return "\n".join(_log_path().read_text().strip().splitlines()[-lines:])
    except OSError:
        return "(no log)"


def _healthy(domain: str) -> bool:
    try:
        with urllib.request.urlopen(f"http://{domain}/health", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _sandbox_count(conn: Connection) -> int | None:
    """Best-effort count of live sandboxes for status display."""
    req = urllib.request.Request(
        f"http://{conn.domain}/v1/sandboxes",
        headers={"OPEN-SANDBOX-API-KEY": conn.api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
    items = body.get("items") if isinstance(body, dict) else body
    return len(items) if isinstance(items, list) else None


__all__ = [
    "DEFAULT_ALLOW_DOMAINS",
    "Connection",
    "SandboxUnavailable",
    "docker_available",
    "ensure_server",
    "network_policy",
    "server_dir",
    "server_status",
    "stop_server",
]
