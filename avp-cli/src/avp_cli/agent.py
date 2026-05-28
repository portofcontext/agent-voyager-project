"""Run a real AVP agent against one Commission and collect its trajectory.

Every conforming AVP agent ships an `avp-conformance.json` manifest and honors
the same run contract the conformance harness uses:

    <manifest.command> run --commission <path> --out <ndjson>

So driving Goose or Claude Code is identical: load the manifest, write the
Commission to a file, spawn the command with the manifest's cwd/env, and read
the NDJSON trajectory back from `--out`. No bespoke per-agent glue.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from avp_conformance.manifest import AgentManifest
from pydantic import BaseModel

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.trajectory import parse_event

# How often the streaming path re-reads the growing --out file (seconds).
_TAIL_INTERVAL = 0.06


def load_manifest(path: str | Path) -> tuple[AgentManifest, Path]:
    """Load an agent manifest and resolve its cwd relative to the manifest file."""
    p = Path(path).resolve()
    manifest = AgentManifest.model_validate(json.loads(p.read_text()))
    cwd = (p.parent / manifest.cwd).resolve()
    return manifest, cwd


def run_agent(
    manifest: AgentManifest,
    manifest_cwd: Path,
    commission: Commission,
    *,
    out_path: str | Path,
    timeout_s: float = 300.0,
    on_event: Callable[[BaseModel | dict[str, Any]], None] | None = None,
) -> tuple[list[BaseModel | dict[str, Any]] | None, str | None]:
    """Run the agent for one Commission. Returns (events, error).

    On success `error` is None and `events` is the parsed NDJSON trajectory
    (custom event types pass through as dicts). On failure `events` is None and
    `error` is a short diagnostic (subprocess nonzero exit, timeout, etc.) so
    one bad run is recorded per-cell rather than aborting the matrix.

    If `on_event` is given, the agent's `--out` file is tailed while it runs and
    `on_event` is called per trajectory event for live progress. The returned
    list is always re-parsed from the finished file, so it stays authoritative
    regardless of what the live tail saw. A `KeyboardInterrupt` terminates the
    child and propagates (the caller decides whether to stop the matrix).
    """
    out = Path(out_path)
    env = {**os.environ, **manifest.env}

    with tempfile.TemporaryDirectory() as tmp:
        commission_path = Path(tmp) / "commission.json"
        commission_path.write_text(commission.model_dump_json(by_alias=True, exclude_none=True))
        cmd = [*manifest.command, "run", "--commission", str(commission_path), "--out", str(out)]
        stderr_path = Path(tmp) / "stderr.log"
        if on_event is None:
            err = _run_blocking(cmd, manifest_cwd, env, timeout_s)
        else:
            err = _run_streaming(cmd, manifest_cwd, env, out, stderr_path, timeout_s, on_event)
        if err is not None:
            return None, err

    if not out.exists():
        return None, "agent exited 0 but wrote no trajectory"
    events: list[BaseModel | dict[str, Any]] = []
    for line in out.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(parse_event(json.loads(line)))
    return events, None


def describe_agent(
    manifest: AgentManifest,
    manifest_cwd: Path,
    *,
    timeout_s: float = 120.0,
) -> tuple[AgentDescriptor | None, str | None]:
    """Fetch an agent's self-description via `<command> describe --out <file>`.

    This is the spec's pre-flight view: the agent boots, lists its surface, and
    exits without a model turn, so it's free. Returns (descriptor, error).
    """
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
    """Spawn and wait; return an error string or None on clean exit."""
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


def _run_streaming(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    out: Path,
    stderr_path: Path,
    timeout_s: float,
    on_event: Callable[[BaseModel | dict[str, Any]], None],
) -> str | None:
    """Spawn, tail the growing `out` file into `on_event`, return error or None.

    The child is always terminated on exit from this function (timeout, error,
    or a propagating KeyboardInterrupt) via the `finally` block.
    """
    with stderr_path.open("w") as errf:
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=errf)
        except OSError as exc:
            return f"spawn failed: {exc}"
        start = time.monotonic()
        pos = 0
        buf = ""
        timed_out = False
        try:
            while True:
                pos, buf = _drain(out, pos, buf, on_event)
                if proc.poll() is not None:
                    break
                if time.monotonic() - start > timeout_s:
                    timed_out = True
                    break
                time.sleep(_TAIL_INTERVAL)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if timed_out:
            return f"timed out after {timeout_s:.0f}s"
        _drain(out, pos, buf, on_event)  # any lines written between last poll and exit

    if proc.returncode != 0:
        tail = "\n".join(stderr_path.read_text().strip().splitlines()[-3:]) or "(no stderr)"
        return f"exit {proc.returncode}: {tail}"
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
