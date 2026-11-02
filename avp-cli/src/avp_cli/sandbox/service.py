"""The local OpenSandbox server: avp writes its config, starts it in the
background, and reuses it across commands until `avp sandbox stop`."""

import json
import os
import secrets
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import httpx
from opensandbox.config import ConnectionConfigSync

from avp_cli import engine, paths
from avp_cli.console import Failed, detail

PORT = 18764
"""Not OpenSandbox's 8080, which other tools often hold, nor the legacy CLI's 18763."""
# The images match the opensandbox 1.2 SDK: older exec daemons can't run a
# command from its arguments, without a shell.
EXECD_IMAGE = "opensandbox/execd:release-1.2.0"
EGRESS_IMAGE = "opensandbox/egress:release-1.2.0"
START_TIMEOUT_S = 30


def config_text(api_key: str) -> str:
    return f"""\
# Written by avp each time it starts the service.
[server]
host = "127.0.0.1"
port = {PORT}
api_key = "{api_key}"
max_sandbox_timeout_seconds = 86400

[runtime]
type = "docker"
execd_image = "{EXECD_IMAGE}"

[storage]
allowed_host_paths = {allowed_host_paths()}

[store]
type = "sqlite"
path = "{paths.opensandbox() / "state.db"}"

[docker]
network_mode = "bridge"
no_new_privileges = true
pids_limit = 4096

[ingress]
mode = "direct"

[egress]
image = "{EGRESS_IMAGE}"
mode = "dns+nft"
"""


def allowed_host_paths() -> str:
    """Any host path, as a TOML list: the server listens only on 127.0.0.1 and
    takes only avp's key, so what is mounted is what avp's commands ask for.
    OpenSandbox matches `prefix + "/"`, so `/` itself would match nothing; each
    directory in `/` is listed instead."""
    root = Path("/")
    return json.dumps(sorted(str(p) for p in root.iterdir() if p.is_dir()))


def connection() -> ConnectionConfigSync:
    """The running service's connection, started first when it isn't running."""
    if not running():
        start()
    return _connection()


def running() -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def config() -> dict | None:
    """The config the service was last started with, or None before the first start."""
    try:
        return tomllib.loads((paths.opensandbox() / "config.toml").read_text())
    except FileNotFoundError:
        return None


def pid() -> int | None:
    """The process avp last started, or None when avp hasn't started one."""
    try:
        return int((paths.opensandbox() / "server.pid").read_text())
    except (FileNotFoundError, ValueError):
        return None


def start() -> None:
    if running():
        detail("OpenSandbox was already running")
        return
    detail(f"Engine: {engine.where()}")
    engine.client()
    directory = paths.opensandbox()
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / "config.toml"
    config.write_text(config_text(secrets.token_hex(32)))
    config.chmod(0o600)
    with (directory / "server.log").open("ab") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "opensandbox_server.cli", "--config", str(config)],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    (directory / "server.pid").write_text(str(server.pid))
    began = time.monotonic()
    deadline = began + START_TIMEOUT_S
    while time.monotonic() < deadline:
        if running():
            detail(f"Started process {server.pid} in {time.monotonic() - began:.1f}s")
            return
        if server.poll() is not None:
            break
        time.sleep(0.25)
    raise Failed(f"the OpenSandbox service didn't start. See {directory / 'server.log'}")


def stop() -> bool:
    """Stop the service avp started. False when it wasn't running."""
    pid_file = paths.opensandbox() / "server.pid"
    if not pid_file.is_file():
        return False
    try:
        process = int(pid_file.read_text())
        os.kill(process, signal.SIGTERM)
    except (ValueError, ProcessLookupError):
        return False
    finally:
        pid_file.unlink()
    detail(f"Stopped process {process}")
    return True


def _connection() -> ConnectionConfigSync:
    api_key = (config() or {})["server"]["api_key"]
    return ConnectionConfigSync(domain=f"127.0.0.1:{PORT}", api_key=api_key, protocol="http")
