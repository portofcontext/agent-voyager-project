"""Spawn an AVP agent subprocess, pipe Commission in, collect events out.

This is the wire-level supervisor: stdin gets one Commission JSON line, stdout
yields NDJSON event lines. Errors on stderr are forwarded so the user sees
why the agent died.

Two entry points:
- `run_subprocess(cmd, commission)`: drives an external agent CLI (e.g. the
  reference avp-anthropic agent in `examples/_anthropic_reference_agent.py`,
  or `avp-claude-agent`).
- `run_in_process(commission, agent_factory)`: drives the reference agent
  directly, for fast unit-test-friendly demos with ScriptedModel.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from typing import Any

from pydantic import BaseModel

from avp import Commission, parse_event


def run_subprocess(
    cmd: list[str],
    commission: Commission,
    *,
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
    rpc_responder: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    timeout_s: float = 120.0,
) -> list[BaseModel | dict[str, Any]]:
    """Run `cmd` (e.g. `[sys.executable, "examples/_anthropic_reference_agent.py"]`
    or `["avp-claude-agent"]`) with Commission piped on stdin.

    Returns the trajectory as parsed Pydantic events. Custom event types pass
    through as raw dicts (per `spec/README.md` §4).

    `rpc_responder` is an optional callback the supervisor uses to service
    tool_exec_request events: it receives the request dict and returns either
    a tool_exec_resolved dict (which is sent over stdin) or None to time out.
    Demo-grade: the responder runs synchronously in this thread.
    """
    import os

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=cwd,
        text=True,
        bufsize=1,
    )
    assert proc.stdin and proc.stdout and proc.stderr

    # Forward stderr to our stderr so users see real errors.
    def _drain_stderr() -> None:
        assert proc.stderr
        for line in proc.stderr:
            sys.stderr.write(f"[agent] {line}")

    threading.Thread(target=_drain_stderr, daemon=True).start()

    proc.stdin.write(commission.model_dump_json(by_alias=True, exclude_none=True) + "\n")
    proc.stdin.flush()

    events: list[BaseModel | dict[str, Any]] = []
    try:
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            payload = json.loads(line)
            ev = parse_event(payload)
            events.append(ev)

            if rpc_responder is not None and payload.get("type") == "avp.tool_exec_request":
                reply = rpc_responder(payload)
                if reply is not None:
                    proc.stdin.write(json.dumps(reply) + "\n")
                    proc.stdin.flush()

            if payload.get("type") == "avp.agent_stopped":
                break

        proc.stdin.close()
        proc.wait(timeout=timeout_s)
    finally:
        if proc.poll() is None:
            proc.terminate()

    return events


def stream_subprocess(
    cmd: list[str],
    commission: Commission,
    *,
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> Iterator[BaseModel | dict[str, Any]]:
    """Yield events as the agent emits them. For long-running supervisor loops."""
    import os

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=cwd,
        text=True,
        bufsize=1,
    )
    assert proc.stdin and proc.stdout and proc.stderr

    # Forward the agent's stderr to our stderr so users see the real reason
    # if the agent dies before emitting agent_stopped. Without this the pipe
    # closes silently and the supervisor's iterator exits cleanly with a
    # truncated trajectory.
    def _drain_stderr() -> None:
        assert proc.stderr
        for line in proc.stderr:
            sys.stderr.write(f"[agent] {line}")

    threading.Thread(target=_drain_stderr, daemon=True).start()

    proc.stdin.write(commission.model_dump_json(by_alias=True, exclude_none=True) + "\n")
    proc.stdin.flush()

    try:
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            payload = json.loads(line)
            yield parse_event(payload)
            if payload.get("type") == "avp.agent_stopped":
                break
    finally:
        proc.stdin.close()
        if proc.poll() is None:
            proc.terminate()
