"""Run a real AVP agent against one Commission, inside a sandbox.

Every conforming AVP agent honors the same run contract the conformance
harness uses:

    <command> run --commission <path> --out <ndjson>

Here that command executes inside an OpenSandbox container built from the
environment's derived image (see `avp_cli.images`): the per-run host workspace
and an io dir are bind-mounted in, the Commission goes in as a file, and the
NDJSON trajectory lands back on the host where it is tailed live and parsed.
The host machine is not part of the agent's world; everything the agent sees
is declared (image, mounts, env vars, egress policy).

`describe_agent` stays a host-side subprocess: it is the free pre-flight view
(no model turn, no tools), driven from the agent's manifest like the
conformance harness does.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from avp_conformance.manifest import AgentManifest
from opensandbox import SandboxSync
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.sandboxes import Host, Volume
from pydantic import BaseModel

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.trajectory import parse_event
from avp_cli import broker, osb, paths, vault

# How often the streaming path re-reads the growing --out file (seconds).
_TAIL_INTERVAL = 0.06

# In-sandbox layout: one rw mount for the (possibly run-shared) workspace, one
# rw mount for this run's io (commission in, trajectory + stderr out).
_WORKSPACE_MNT = "/avp/workspace"
_IO_MNT = "/avp/io"

# Host env vars forwarded into the sandbox: model-provider credentials and
# agent routing knobs. CLAUDE_ covers CLAUDE_CODE_OAUTH_TOKEN (the
# `claude setup-token` subscription credential the claude CLI accepts in
# place of an API key). The rest of the host environment stays on the host;
# the sandbox env is otherwise fully declared.
_ENV_PASSTHROUGH_PREFIXES = (
    "ANTHROPIC_",
    "CLAUDE_",
    "OPENAI_",
    "GOOGLE_",
    "GEMINI_",
    "MISTRAL_",
    "OPENROUTER_",
    "GOOSE_",
)

# Sandbox lifetime margin beyond the run timeout: covers image boot, setup
# commands, and trajectory readback before the server reaps the sandbox.
_SANDBOX_TTL_MARGIN_S = 180.0

_DEFAULT_RESOURCES = {"cpu": "2", "memory": "4Gi"}


@dataclass(frozen=True)
class SandboxedAgent:
    """An agent resolved to its in-sandbox form: the derived image that has it
    installed, the argv that runs it there, and its manifest env."""

    name: str
    image: str
    command: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class SandboxContext:
    """The run-level sandbox facts shared by every cell of an eval (or the one
    cell of `avp run`): server connection, the seeded host workspace, and the
    environment's setup / egress / resource asks."""

    connection: osb.Connection
    workspace: Path
    setup: list[str] = field(default_factory=list)
    net: list[str] = field(default_factory=list)
    resources: dict[str, str] = field(default_factory=dict)


def load_manifest(path: str | Path) -> tuple[AgentManifest, Path]:
    """Load an agent manifest and resolve its cwd relative to the manifest file."""
    p = Path(path).resolve()
    manifest = AgentManifest.model_validate(json.loads(p.read_text()))
    cwd = (p.parent / manifest.cwd).resolve()
    return manifest, cwd


def run_agent(
    agent: SandboxedAgent,
    ctx: SandboxContext,
    commission: Commission,
    *,
    out_path: str | Path,
    timeout_s: float = 300.0,
    on_event: Callable[[BaseModel | dict[str, Any]], None] | None = None,
) -> tuple[list[BaseModel | dict[str, Any]] | None, str | None]:
    """Run the agent for one Commission in a fresh sandbox. Returns (events, error).

    On success `error` is None and `events` is the parsed NDJSON trajectory
    (custom event types pass through as dicts). On failure `events` is None and
    `error` is a short diagnostic (nonzero exit, timeout, sandbox create
    failure) so one bad run is recorded per-cell rather than aborting a matrix.

    If `on_event` is given, the trajectory file is tailed on the host (through
    the io bind mount) while the agent runs and `on_event` fires per event for
    live progress. The returned list is always re-parsed from the finished
    file, so it stays authoritative regardless of what the live tail saw.

    The sandbox is always killed before returning; the workspace mount is the
    only place agent writes survive.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # io lives under ~/.avp: the server's allowed_host_paths confines bind
    # mounts there, and --out may point anywhere on the host. The trajectory
    # is moved to `out` once the run settles.
    io_dir = paths.avp_home() / "tmp" / uuid.uuid4().hex
    io_dir.mkdir(parents=True)
    traj_host = io_dir / "trajectory.ndjson"

    # Vault broker: when the Commission references any secret (provider
    # credential or MCP auth), a host-side credential-injecting proxy serves
    # those endpoints so the resolved value never enters the sandbox. The
    # written commission + sandbox env then point at the broker with sentinels.
    brk: broker.Broker | None = None
    try:
        brk = _start_broker(commission)
    except vault.VaultError as exc:
        shutil.rmtree(io_dir, ignore_errors=True)
        return None, f"vault: {exc}"
    except Exception as exc:
        shutil.rmtree(io_dir, ignore_errors=True)
        return None, f"vault broker startup failed: {exc}"

    try:
        (io_dir / "commission.json").write_text(_commission_for_sandbox(commission, brk))
        try:
            box = SandboxSync.create(
                agent.image,
                connection_config=ctx.connection.config(),
                env=_sandbox_env(agent, commission, brk),
                volumes=[
                    Volume(
                        name="workspace",
                        host=Host(path=str(ctx.workspace.resolve())),
                        mount_path=_WORKSPACE_MNT,
                    ),
                    Volume(name="io", host=Host(path=str(io_dir)), mount_path=_IO_MNT),
                ],
                # Egress is default-deny floored by runtime-base domains, plus the
                # env's `net`, plus the hosts the run reaches: under broker mode
                # just the broker host (the broker reaches providers/MCP from the
                # host); otherwise the provider + MCP hosts the Commission names.
                # A run can never be commissioned to call a URL the sandbox blocks.
                network_policy=osb.network_policy([*ctx.net, *_egress_extra(commission, brk)]),
                resource={**_DEFAULT_RESOURCES, **ctx.resources},
                timeout=timedelta(seconds=timeout_s + _SANDBOX_TTL_MARGIN_S),
            )
        except Exception as exc:
            return None, f"sandbox create failed: {exc}"
        try:
            # Fail closed: if the vault broker isn't reachable from the sandbox,
            # refuse the run rather than ever placing the secret inside it.
            err = _preflight_broker(box, brk) if brk is not None else None
            if err is None:
                err = _run_setup(box, ctx.setup)
            if err is None:
                argv = [
                    *agent.command,
                    "run",
                    "--commission",
                    f"{_IO_MNT}/commission.json",
                    "--out",
                    f"{_IO_MNT}/trajectory.ndjson",
                ]
                command = f"{shlex.join(argv)} 2>{_IO_MNT}/stderr.log"
                if on_event is None:
                    err = _exec(box, command, timeout_s, io_dir)
                else:
                    err = _exec_streaming(box, command, timeout_s, io_dir, traj_host, on_event)
        finally:
            with contextlib.suppress(Exception):  # reaped by TTL if the kill call fails
                box.kill()
        if err is not None:
            return None, err
        if not traj_host.exists():
            return None, "agent exited 0 but wrote no trajectory"
        if traj_host != out:
            shutil.move(traj_host, out)
        return read_trajectory(out), None
    finally:
        if brk is not None:
            brk.stop()
        shutil.rmtree(io_dir, ignore_errors=True)


# The sentinel key the agent receives in place of a vault-managed credential.
# Non-empty so SDKs that require a key present are satisfied; the broker
# overwrites it with the real value on the host before forwarding.
_VAULT_SENTINEL = "avp-vault-managed"


def _provider_credentialed(commission: Commission) -> bool:
    p = commission.provider
    return p is not None and p.credential is not None


def _start_broker(commission: Commission) -> broker.Broker | None:
    """Start a vault broker iff the Commission references any secret. Resolves
    handles host-side (may raise VaultError); secrets live only in the broker."""
    routes: list[tuple[str, broker.Route]] = []
    prov = commission.provider
    if _provider_credentialed(commission):
        base = prov.base_url or (osb.PROVIDER_REGISTRY.get(prov.id) or (None, None))[1] or ""
        header, prefix = (
            ("x-api-key", "") if prov.id == "anthropic" else ("authorization", "Bearer ")
        )
        routes.append(
            (
                f"llm/{prov.id}",
                broker.Route(
                    upstream=broker.origin_of(base),
                    header=header,
                    prefix=prefix,
                    secret=vault.resolve_ref(prov.credential),
                ),
            )
        )
    for server in commission.mcp_servers or []:
        auth = getattr(server, "auth", None)
        if auth is not None:
            routes.append(
                (
                    f"mcp/{server.id}",
                    broker.Route(
                        upstream=server.url,
                        header="authorization",
                        prefix="Bearer ",
                        secret=vault.resolve(auth.vault),
                    ),
                )
            )
    if not routes:
        return None
    brk = broker.Broker()
    for key, route in routes:
        brk.add_route(key, route)
    brk.start()
    return brk


def _sandbox_env(
    agent: SandboxedAgent, commission: Commission, brk: broker.Broker | None
) -> dict[str, str]:
    """The declared sandbox environment: provider routing (broker urls +
    sentinels for vault-credentialed providers, real base_url otherwise), the
    manifest's env, and the AVP workspace convention (AVP_WORKSPACE /
    AVP_ENV_ROOT). Host provider vars (ANTHROPIC_*, …) are forwarded for the
    no-vault case where the user supplies their own ambient key.
    """
    env = {k: v for k, v in os.environ.items() if k.startswith(_ENV_PASSTHROUGH_PREFIXES)}
    prov = commission.provider
    if prov is not None:
        up = prov.id.upper().replace("-", "_")
        if prov.credential is not None and brk is not None:
            # Vault: route through the broker, hand the agent only a sentinel.
            route = brk.route_url(f"llm/{prov.id}")
            if prov.id == "anthropic":
                env["ANTHROPIC_BASE_URL"] = route
                env["ANTHROPIC_API_KEY"] = _VAULT_SENTINEL
            else:
                env[f"{up}_HOST"] = route
                env[f"{up}_API_KEY"] = _VAULT_SENTINEL
                env["GOOSE_PROVIDER"] = prov.id
        else:
            # Non-vault provider: real endpoint, ambient key (forwarded above).
            base = prov.base_url or (osb.PROVIDER_REGISTRY.get(prov.id) or (None, None))[1]
            if prov.id == "anthropic":
                if base:
                    env["ANTHROPIC_BASE_URL"] = base
            else:
                if base:
                    env[f"{up}_HOST"] = base
                env["GOOSE_PROVIDER"] = prov.id
    env.update(agent.env)
    env["AVP_WORKSPACE"] = _WORKSPACE_MNT
    env["AVP_ENV_ROOT"] = "/avp"
    return env


def _commission_for_sandbox(commission: Commission, brk: broker.Broker | None) -> str:
    """The commission.json the agent reads.

    Provider routing and MCP auth are supervisor concerns the CLI delivers via
    env (`_sandbox_env`) and the broker, not fields the agent consumes — so they
    are stripped from what the agent receives. This also keeps the written
    commission compatible with released agents whose (older) wire types reject
    unknown fields like `provider`/`auth`, and keeps the resolved value out of
    the agent's run_requested snapshot. Under broker mode each authed MCP url is
    rewritten to its broker route (the broker injects the credential)."""
    data = commission.model_dump(by_alias=True, exclude_none=True, mode="json")
    data.pop("provider", None)
    for server in data.get("mcp_servers") or []:
        if brk is not None and server.get("type") == "http" and server.get("auth") is not None:
            server["url"] = brk.route_url(f"mcp/{server['id']}")
        server.pop("auth", None)
    return json.dumps(data)


def _egress_extra(commission: Commission, brk: broker.Broker | None) -> list[str]:
    """Per-run egress additions. Without a broker: the provider + MCP hosts the
    Commission names. With a broker: the broker host, plus the hosts of any
    endpoints NOT routed through it (non-credentialed provider / unauthed MCP)."""
    if brk is None:
        return osb.commission_egress_hosts(commission)
    hosts = [broker.SANDBOX_HOST_ALIAS]
    prov = commission.provider
    if prov is not None and prov.credential is None:
        base = prov.base_url or (osb.PROVIDER_REGISTRY.get(prov.id) or (None, None))[1]
        if base:
            hosts.append(urlparse(base).hostname or "")
    for server in commission.mcp_servers or []:
        if getattr(server, "url", None) and getattr(server, "auth", None) is None:
            hosts.append(urlparse(server.url).hostname or "")
    return [h for h in hosts if h]


def _preflight_broker(box: SandboxSync, brk: broker.Broker) -> str | None:
    """Confirm the sandbox can reach the vault broker before the agent runs.
    Returns an error string (fail closed) when it can't; never falls back to
    placing the secret in the sandbox."""
    url = f"{brk.base_url()}/health"
    probe = (
        f'curl -fsS -m 5 "{url}" >/dev/null 2>&1 '
        f'|| wget -q -T 5 -O - "{url}" >/dev/null 2>&1 '
        f'|| python3 -c "import urllib.request as u,sys; u.urlopen(sys.argv[1],timeout=5)" "{url}"'
    )
    try:
        execution = box.commands.run(
            f"sh -c {shlex.quote(probe)}",
            opts=RunCommandOpts(timeout=timedelta(seconds=20)),
        )
    except Exception as exc:
        return f"vault broker preflight failed to run ({exc}); refusing to run"
    if execution.exit_code not in (0, None):
        return (
            "vault broker unreachable from the sandbox "
            f"({brk.base_url()}); refusing to run rather than expose the secret"
        )
    return None


def _run_setup(box: SandboxSync, setup: list[str]) -> str | None:
    """Run the env's setup commands in the workspace; first failure reports."""
    for command in setup:
        try:
            execution = box.commands.run(
                command,
                opts=RunCommandOpts(
                    working_directory=_WORKSPACE_MNT, timeout=timedelta(minutes=10)
                ),
            )
        except Exception as exc:
            return f"setup failed ({command!r}): {exc}"
        if execution.exit_code not in (0, None):
            tail = _logs_tail(execution)
            return f"setup exit {execution.exit_code} ({command!r}): {tail}"
    return None


def _exec(box: SandboxSync, command: str, timeout_s: float, io_dir: Path) -> str | None:
    """Run the agent command and wait; return an error string or None."""
    try:
        execution = box.commands.run(
            command,
            opts=RunCommandOpts(
                working_directory=_WORKSPACE_MNT, timeout=timedelta(seconds=timeout_s)
            ),
        )
    except Exception as exc:
        return _timeout_or(f"agent run failed: {exc}", exc, timeout_s)
    return _exit_error(execution, io_dir)


def _exec_streaming(
    box: SandboxSync,
    command: str,
    timeout_s: float,
    io_dir: Path,
    traj_host: Path,
    on_event: Callable[[BaseModel | dict[str, Any]], None],
) -> str | None:
    """Run the agent command in a worker thread while tailing the growing
    trajectory file (visible on the host through the io bind mount)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_exec, box, command, timeout_s, io_dir)
        deadline = time.monotonic() + timeout_s + _SANDBOX_TTL_MARGIN_S
        pos = 0
        buf = ""
        try:
            while not future.done():
                pos, buf = _drain(traj_host, pos, buf, on_event)
                if time.monotonic() > deadline:  # belt-and-suspenders over execd's timeout
                    return f"timed out after {timeout_s:.0f}s"
                time.sleep(_TAIL_INTERVAL)
        except KeyboardInterrupt:
            with contextlib.suppress(Exception):
                box.kill()  # unblocks the worker; the caller decides what stops
            raise
        _drain(traj_host, pos, buf, on_event)  # lines written between last poll and exit
        return future.result()


def _exit_error(execution: Any, io_dir: Path) -> str | None:
    if execution.exit_code in (0, None):
        return None
    stderr = io_dir / "stderr.log"
    tail = ""
    if stderr.exists():
        tail = "\n".join(stderr.read_text().strip().splitlines()[-3:])
    return f"exit {execution.exit_code}: {tail or _logs_tail(execution) or '(no stderr)'}"


def _logs_tail(execution: Any, lines: int = 3) -> str:
    chunks = [log.text for log in (execution.logs.stderr or execution.logs.stdout or [])]
    return "\n".join("".join(chunks).strip().splitlines()[-lines:])


def _timeout_or(message: str, exc: Exception, timeout_s: float) -> str:
    """execd surfaces a run timeout as an SDK exception; report it as ours."""
    if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
        return f"timed out after {timeout_s:.0f}s"
    return message


def read_trajectory(path: Path) -> list[BaseModel | dict[str, Any]]:
    """Parse a finished NDJSON trajectory file into events (custom types as dicts).

    The inverse of what an agent's `--out` stream produces; used both to return a
    run's events and to re-read a previously completed run for `--resume`.
    """
    events: list[BaseModel | dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(parse_event(json.loads(line)))
    return events


def describe_agent(
    manifest: AgentManifest,
    manifest_cwd: Path,
    *,
    timeout_s: float = 120.0,
) -> tuple[AgentDescriptor | None, str | None]:
    """Fetch an agent's self-description via `<command> describe --out <file>`.

    This is the spec's pre-flight view: the agent boots, lists its surface, and
    exits without a model turn, so it's free, and it runs on the host (no
    sandbox; nothing untrusted executes).
    """
    import tempfile

    env = {**os.environ, **manifest.env}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "descriptor.json"
        cmd = [*manifest.command, "describe", "--out", str(out)]
        err = _run_blocking(cmd, manifest_cwd, env, timeout_s)
        if err is not None:
            return None, err
        if not out.exists():
            return None, "agent exited 0 but wrote no descriptor"
        try:
            return AgentDescriptor.model_validate(json.loads(out.read_text())), None
        except Exception as exc:  # malformed / not a descriptor
            return None, f"unparseable descriptor: {exc}"


def _run_blocking(cmd: list[str], cwd: Path, env: dict[str, str], timeout_s: float) -> str | None:
    """Spawn a host subprocess and wait; return an error string or None."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout_s
        )
    except subprocess.TimeoutExpired:
        return f"timed out after {timeout_s:.0f}s"
    except OSError as exc:
        return f"spawn failed: {exc}"
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-3:]) or "(no stderr)"
        return f"exit {result.returncode}: {tail}"
    return None


def _drain(
    out: Path, pos: int, buf: str, on_event: Callable[[BaseModel | dict[str, Any]], None]
) -> tuple[int, str]:
    """Read `out` from byte offset `pos`, emit each complete NDJSON line to
    `on_event`. Returns the new offset and any trailing partial line."""
    if not out.exists():
        return pos, buf
    try:
        with out.open("r") as f:
            f.seek(pos)
            buf += f.read()
            pos = f.tell()
    except (OSError, UnicodeDecodeError):
        return pos, buf  # transient (mid-write / partial multibyte); retry next tick
    while "\n" in buf:
        line, buf = buf.split("\n", 1)
        line = line.strip()
        if not line:
            continue
        # A partial line or a live-display glitch must not abort the run; the
        # final full-file parse in run_agent is authoritative anyway.
        with contextlib.suppress(Exception):
            on_event(parse_event(json.loads(line)))
    return pos, buf
