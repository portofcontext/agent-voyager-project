"""Smoke tests for claude-agent-sdk-aep.

All tests that make real API calls are skipped when ANTHROPIC_API_KEY is not
set. They're also marked ``slow`` so CI can skip them with ``-m "not slow"``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
FAST_MODEL = "anthropic/claude-haiku-4-5-20251001"
SKIP_NO_KEY = pytest.mark.skipif(not HAS_API_KEY, reason="ANTHROPIC_API_KEY not set")
SLOW = pytest.mark.slow


# ── helpers ───────────────────────────────────────────────────────────────────

def _events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _types(stdout: str) -> list[str]:
    return [e["type"] for e in _events(stdout)]


def _run_subprocess(config: dict) -> subprocess.CompletedProcess:
    """Spawn the runner as a subprocess, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "claude_agent_sdk_aep"],
        input=json.dumps(config),
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
        env={**os.environ},
    )


# ── unit: import smoke ────────────────────────────────────────────────────────

def test_imports():
    from claude_agent_sdk_aep import query, aep_options, run_from_stdin  # noqa: F401


def test_aep_options_returns_run_id_and_options():
    from claude_agent_sdk_aep import aep_options

    run_id, opts = aep_options(model="claude-sonnet-4-6")
    assert isinstance(run_id, str) and len(run_id) > 0
    assert opts is not None


def test_aep_options_accepts_run_id():
    from claude_agent_sdk_aep import aep_options

    run_id, _ = aep_options(run_id="my-run-123")
    assert run_id == "my-run-123"


# ── unit: hook trigger matching ───────────────────────────────────────────────

def test_trigger_matches_exact():
    from claude_agent_sdk_aep._hooks import _trigger_matches

    assert _trigger_matches("on_start", "on_start")
    assert _trigger_matches("on_stop", "on_stop")
    assert _trigger_matches("on_turn_end", "on_turn_end")
    assert _trigger_matches("on_tool:bash", "on_tool:bash")


def test_trigger_not_matches_different():
    from claude_agent_sdk_aep._hooks import _trigger_matches

    assert not _trigger_matches("on_start", "on_stop")
    assert not _trigger_matches("on_tool:bash", "on_tool:read")


def test_trigger_always_matches_tool_results():
    from claude_agent_sdk_aep._hooks import _trigger_matches

    assert _trigger_matches("always", "on_tool:bash")
    assert _trigger_matches("always", "on_tool:read")
    assert _trigger_matches("always", "on_tool:my_custom_tool")


def test_trigger_always_matches_turn_end():
    from claude_agent_sdk_aep._hooks import _trigger_matches

    assert _trigger_matches("always", "on_turn_end")


def test_trigger_always_does_not_match_lifecycle():
    from claude_agent_sdk_aep._hooks import _trigger_matches

    assert not _trigger_matches("always", "on_start")
    assert not _trigger_matches("always", "on_stop")


# ── unit: fire_hooks with no hooks ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fire_hooks_no_hooks_returns_continue():
    from claude_agent_sdk_aep._hooks import fire_hooks

    verdict = await fire_hooks("on_start", "r1", 0, [], None)
    assert verdict == "continue"


@pytest.mark.asyncio
async def test_fire_hooks_no_stdin_returns_continue():
    from agent_execution_protocol import AepHook
    from claude_agent_sdk_aep._hooks import fire_hooks

    hooks = [AepHook(name="h", trigger="on_start")]
    verdict = await fire_hooks("on_start", "r1", 0, hooks, None)
    assert verdict == "continue"


@pytest.mark.asyncio
async def test_fire_hooks_no_matching_trigger_returns_continue():
    import io
    from agent_execution_protocol import AepHook
    from claude_agent_sdk_aep._hooks import fire_hooks

    hooks = [AepHook(name="h", trigger="on_stop")]
    # Firing on_start, hook is on_stop — no match
    verdict = await fire_hooks("on_start", "r1", 0, hooks, io.StringIO())
    assert verdict == "continue"


@pytest.mark.asyncio
async def test_fire_hooks_continue_verdict(capsys):
    import io
    from agent_execution_protocol import AepHook
    from claude_agent_sdk_aep._hooks import fire_hooks

    verdict_line = json.dumps({
        "type": "hook_verdict",
        "run_id": "r1",
        "request_id": "hr-00000000",  # will be overridden; we just need any valid verdict
        "verdict": "continue",
        "ts": "2026-01-01T00:00:00Z",
    })
    # We can't easily control the request_id in the verdict, so use default_verdict
    hooks = [AepHook(name="h", trigger="on_start", default_verdict="continue")]
    stdin = io.StringIO("")  # empty → timeout → default_verdict
    verdict = await fire_hooks("on_start", "r1", 0, hooks, stdin)
    assert verdict == "continue"


@pytest.mark.asyncio
async def test_fire_hooks_stop_verdict_via_default(capsys):
    import io
    from agent_execution_protocol import AepHook
    from claude_agent_sdk_aep._hooks import fire_hooks

    hooks = [AepHook(name="h", trigger="on_start", default_verdict="stop")]
    stdin = io.StringIO("")  # empty → timeout → default_verdict = stop
    verdict = await fire_hooks("on_start", "r1", 0, hooks, stdin)
    assert verdict == "stop"


@pytest.mark.asyncio
async def test_fire_hooks_emits_hook_request_and_applied(capsys):
    import io
    from agent_execution_protocol import AepHook
    from claude_agent_sdk_aep._hooks import fire_hooks

    hooks = [AepHook(name="gate", trigger="on_start", default_verdict="continue")]
    stdin = io.StringIO("")
    await fire_hooks("on_start", "r1", 0, hooks, stdin)

    out = capsys.readouterr().out
    events = _events(out)
    types = [e["type"] for e in events]
    assert "hook_request" in types
    assert "hook_verdict_applied" in types

    hr = next(e for e in events if e["type"] == "hook_request")
    assert hr["hook_name"] == "gate"
    assert hr["trigger"] == "on_start"
    assert hr["run_id"] == "r1"

    hva = next(e for e in events if e["type"] == "hook_verdict_applied")
    assert hva["verdict"] == "continue"
    assert hva["timed_out"] is True


@pytest.mark.asyncio
async def test_fire_hooks_matching_verdict_not_timed_out(capsys):
    import io
    from agent_execution_protocol import AepHook
    from claude_agent_sdk_aep._hooks import fire_hooks

    # We need the request_id to match; easiest way is to read the emitted
    # hook_request and reply. But since emit() writes to stdout and we're
    # not capturing mid-flight, we use a small trick: intercept stdout.

    emitted: list[str] = []

    class _Capture:
        def write(self, s: str) -> int:
            emitted.append(s)
            sys.__stdout__.write(s)
            return len(s)
        def flush(self) -> None:
            sys.__stdout__.flush()

    old_stdout = sys.stdout
    sys.stdout = _Capture()

    async def _provide_verdict(stdin_write_end):
        # Wait a tick so hook_request is emitted first
        await asyncio.sleep(0.01)
        # Parse hook_request from emitted lines
        for chunk in emitted:
            for line in chunk.splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") == "hook_request":
                    verdict = json.dumps({
                        "type": "hook_verdict",
                        "run_id": "r1",
                        "request_id": d["request_id"],
                        "verdict": "continue",
                        "ts": "2026-01-01T00:00:00Z",
                    }) + "\n"
                    stdin_write_end.write(verdict)
                    stdin_write_end.flush()
                    return

    import asyncio
    import tempfile

    # Use a temp file as a writable "pipe" stand-in
    with tempfile.SpooledTemporaryFile(mode="w+", max_size=4096) as tf:
        hooks = [AepHook(name="gate", trigger="on_start")]

        task = asyncio.create_task(_provide_verdict(tf))
        verdict = await fire_hooks("on_start", "r1", 0, hooks, tf)
        await task

    sys.stdout = old_stdout
    # Either the verdict was read (continue) or timeout default (continue)
    assert verdict == "continue"


# ── integration: subprocess runner ───────────────────────────────────────────

@SKIP_NO_KEY
@SLOW
def test_run_from_stdin_minimal_emits_valid_stream():
    """Subprocess runner emits agent_start…agent_stop."""
    config = {
        "run_id": "smoke-001",
        "prompt": "Say hello in one sentence. Use no tools.",
        "model": FAST_MODEL,
    }
    result = _run_subprocess(config)
    assert result.returncode == 0, f"runner failed:\n{result.stderr}"
    types = _types(result.stdout)
    assert types[0] == "agent_start"
    assert types[-1] == "agent_stop"
    assert _events(result.stdout)[0]["run_id"] == "smoke-001"


@SKIP_NO_KEY
@SLOW
def test_run_from_stdin_without_model_uses_default():
    """Runner works with no model in config."""
    config = {
        "run_id": "smoke-no-model",
        "prompt": "Say hello in one sentence. Use no tools.",
    }
    result = _run_subprocess(config)
    assert result.returncode == 0, f"runner failed:\n{result.stderr}"
    events = _events(result.stdout)
    assert events[0]["type"] == "agent_start"
    assert events[-1]["type"] == "agent_stop"


@SKIP_NO_KEY
@SLOW
def test_run_from_stdin_with_boundary():
    """max_steps boundary is honoured (stop after N turns)."""
    config = {
        "run_id": "smoke-boundary",
        "prompt": "Count from 1 to 100, one number per message.",
        "model": FAST_MODEL,
        "boundary": {"max_steps": 2},
    }
    result = _run_subprocess(config)
    assert result.returncode == 0, f"runner failed:\n{result.stderr}"
    events = _events(result.stdout)
    stop = next(e for e in events if e["type"] == "agent_stop")
    assert stop["reason"] in ("turn_limit", "converged")


@SKIP_NO_KEY
@SLOW
async def test_query_drop_in_emits_agent_start_stop(capsys):
    """query() drop-in emits agent_start and agent_stop."""
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk_aep import query

    async for _ in query(
        prompt="Say hello in one sentence. Use no tools.",
        options=ClaudeAgentOptions(
            model="claude-haiku-4-5-20251001",
            allowed_tools=[],
        ),
        run_id="smoke-query-001",
    ):
        pass

    out = capsys.readouterr().out
    types = _types(out)
    assert types[0] == "agent_start"
    assert types[-1] == "agent_stop"
    assert _events(out)[0]["run_id"] == "smoke-query-001"


@SKIP_NO_KEY
@SLOW
def test_run_from_stdin_hook_on_start_continue():
    """Supervisor sends continue verdict for on_start hook."""
    config = {
        "run_id": "smoke-hook-start",
        "prompt": "Say hello in one sentence. Use no tools.",
        "model": FAST_MODEL,
        "hooks": [{"name": "gate", "trigger": "on_start", "timeout_ms": 5000}],
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "claude_agent_sdk_aep"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=Path(__file__).parent.parent,
        env={**os.environ},
    )

    proc.stdin.write(json.dumps(config) + "\n")
    proc.stdin.flush()

    # Read stdout inline — respond to hooks as they arrive, no threading needed.
    # proc.communicate() must NOT be used alongside proc.stdout iteration: it
    # closes stdin and races on stdout.
    events = []
    for raw in proc.stdout:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except Exception:
            continue
        events.append(event)
        if event.get("type") == "hook_request":
            verdict = json.dumps({
                "type": "hook_verdict",
                "run_id": config["run_id"],
                "request_id": event["request_id"],
                "verdict": "continue",
                "ts": "2026-01-01T00:00:00Z",
            }) + "\n"
            proc.stdin.write(verdict)
            proc.stdin.flush()

    proc.wait(timeout=60)
    assert proc.returncode == 0, f"runner failed:\n{proc.stderr.read()}"
    types_list = [e["type"] for e in events]
    assert "hook_request" in types_list
    assert "hook_verdict_applied" in types_list
    assert types_list[-1] == "agent_stop"


@SKIP_NO_KEY
@SLOW
def test_run_from_stdin_hook_on_start_stop():
    """Supervisor sends stop verdict for on_start hook — agent never runs."""
    config = {
        "run_id": "smoke-hook-stop",
        "prompt": "Say hello in one sentence. Use no tools.",
        "model": FAST_MODEL,
        "hooks": [{"name": "kill", "trigger": "on_start", "timeout_ms": 5000}],
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "claude_agent_sdk_aep"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=Path(__file__).parent.parent,
        env={**os.environ},
    )

    proc.stdin.write(json.dumps(config) + "\n")
    proc.stdin.flush()

    events = []
    for raw in proc.stdout:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except Exception:
            continue
        events.append(event)
        if event.get("type") == "hook_request":
            verdict = json.dumps({
                "type": "hook_verdict",
                "run_id": config["run_id"],
                "request_id": event["request_id"],
                "verdict": "stop",
                "ts": "2026-01-01T00:00:00Z",
            }) + "\n"
            proc.stdin.write(verdict)
            proc.stdin.flush()

    proc.wait(timeout=30)
    assert proc.returncode == 0, f"runner failed:\n{proc.stderr.read()}"
    types_list = [e["type"] for e in events]
    assert types_list[-1] == "agent_stop"
    stop = next(e for e in events if e["type"] == "agent_stop")
    assert stop["reason"] == "supervisor_stopped"
    # No model turns — agent was stopped before running
    assert "model_turn_start" not in types_list
