"""AEP tool-event emission and supervisor hook firing."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, IO

from agent_execution_protocol import (
    AepHook,
    emit,
    emit_tool_call,
    emit_tool_result,
    emit_hook_request,
    emit_hook_verdict_applied,
    emit_tool_exec_request,
    emit_tool_exec_applied,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ms() -> int:
    return int(time.monotonic() * 1000)


# ── Supervisor hook firing ─────────────────────────────────────────────────────


async def fire_hooks(
    trigger: str,
    run_id: str,
    step: int,
    aep_hooks: list[AepHook],
    hook_stdin: IO[str] | None,
    *,
    call_id: str | None = None,
) -> str:
    """Fire all AEP hooks matching *trigger*; return 'stop' if any says stop.

    Iterates hooks in declaration order. Each matching hook gets its own
    ``hook_request`` / ``hook_verdict_applied`` pair. A single ``stop`` verdict
    short-circuits and returns immediately. ``inject`` verdicts are applied as
    continue (future work — requires SDK support for mid-run message injection).
    """
    if not aep_hooks or hook_stdin is None:
        return "continue"

    for hook in aep_hooks:
        if not _trigger_matches(hook.trigger, trigger):
            continue

        request_id = f"hr-{uuid.uuid4().hex[:8]}"

        emit_hook_request(
            run_id=run_id,
            request_id=request_id,
            hook_name=hook.name,
            trigger=hook.trigger,
            step=step,
            timeout_ms=hook.timeout_ms,
            call_id=call_id,
        )

        verdict, timed_out = await _read_verdict(hook, request_id, hook_stdin)

        emit_hook_verdict_applied(
            run_id=run_id,
            request_id=request_id,
            verdict=verdict,
            timed_out=timed_out,
        )

        if verdict == "stop":
            return "stop"

        if verdict == "inject":
            sys.stderr.write(
                f"[aep] hook '{hook.name}': inject verdict not yet supported,"
                " treating as continue\n"
            )

    return "continue"


async def _read_verdict(
    hook: AepHook,
    request_id: str,
    stdin: IO[str],
) -> tuple[str, bool]:
    """Read one hook_verdict line from *stdin* with timeout.

    Returns ``(verdict, timed_out)``. Falls back to ``hook.default_verdict``
    on timeout, empty input, or any parse error.
    """
    loop = asyncio.get_event_loop()
    try:
        line = await asyncio.wait_for(
            loop.run_in_executor(None, stdin.readline),
            timeout=hook.timeout_ms / 1000,
        )
    except asyncio.TimeoutError:
        return hook.default_verdict, True

    if not line or not line.strip():
        return hook.default_verdict, True

    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        sys.stderr.write(f"[aep] invalid JSON while waiting for verdict: {line!r}\n")
        return hook.default_verdict, True

    if d.get("type") != "hook_verdict":
        sys.stderr.write(
            f"[aep] unexpected message type '{d.get('type')}' waiting for verdict\n"
        )
        return hook.default_verdict, True

    if d.get("request_id") != request_id:
        sys.stderr.write(
            f"[aep] verdict request_id mismatch: got '{d.get('request_id')}'"
            f" expected '{request_id}'\n"
        )
        return hook.default_verdict, True

    verdict = d.get("verdict", hook.default_verdict)
    return verdict, False


def _trigger_matches(hook_trigger: str, fired_trigger: str) -> bool:
    """Return True if *hook_trigger* should fire for *fired_trigger*.

    ``always`` fires after every tool result and every model turn end,
    but NOT at on_start or on_stop.
    """
    if hook_trigger == "always":
        return fired_trigger == "on_turn_end" or fired_trigger.startswith("on_tool:")
    return hook_trigger == fired_trigger


# ── Supervisor tool execution ──────────────────────────────────────────────────


async def read_tool_exec_result(
    call_id: str,
    stdin: IO[str],
    timeout_ms: int = 30000,
) -> tuple[str, bool]:
    """Read one tool_exec_result from stdin with timeout.

    Returns ``(output, timed_out)``. Falls back to ``""`` on timeout or error.
    """
    loop = asyncio.get_event_loop()
    try:
        line = await asyncio.wait_for(
            loop.run_in_executor(None, stdin.readline),
            timeout=timeout_ms / 1000,
        )
    except asyncio.TimeoutError:
        return "", True

    if not line or not line.strip():
        return "", True

    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        sys.stderr.write(f"[aep] invalid JSON for tool_exec_result: {line!r}\n")
        return "", True

    if d.get("type") != "tool_exec_result":
        sys.stderr.write(
            f"[aep] unexpected message type '{d.get('type')}' waiting for tool_exec_result\n"
        )
        return "", True

    if d.get("call_id") != call_id:
        sys.stderr.write(
            f"[aep] call_id mismatch: got '{d.get('call_id')}' expected '{call_id}'\n"
        )
        return "", True

    if d.get("error"):
        return f"Error: {d['error']}", False

    return d.get("output", ""), False


# ── SDK hook builders ──────────────────────────────────────────────────────────


def build_tool_hooks(
    run_id: str,
    step_ref: list[int],
    aep_hooks: list[AepHook],
    hook_stdin: IO[str] | None,
    stop_flag: list[bool],
) -> dict:
    """Return a Claude Agent SDK hooks dict that emits AEP tool events.

    Also fires supervisor hooks after each tool result (``on_tool:<name>``
    and ``always`` triggers). Sets ``stop_flag[0] = True`` if a hook verdict
    requests a stop so the outer query loop can break cleanly.
    """
    call_timers: dict[str, int] = {}

    async def pre_tool_use(input_data: dict, tool_use_id: str | None, ctx: Any) -> dict:
        step_ref[0] += 1
        call_id = tool_use_id or str(uuid.uuid4())[:8]
        call_timers[call_id] = _ms()
        emit_tool_call(
            run_id=run_id,
            step=step_ref[0],
            call_id=call_id,
            tool=input_data["tool_name"],
            input=input_data.get("tool_input", {}),
        )
        return {}

    async def post_tool_use(
        input_data: dict, tool_use_id: str | None, ctx: Any
    ) -> dict:
        call_id = tool_use_id or "unknown"
        start = call_timers.pop(call_id, _ms())
        raw = input_data.get("tool_response") or input_data.get("tool_result") or {}
        tool_name = input_data["tool_name"]

        emit_tool_result(
            run_id=run_id,
            step=step_ref[0],
            call_id=call_id,
            tool=tool_name,
            output=_extract_output(raw),
            duration_ms=_ms() - start,
        )

        # Fire supervisor hooks: on_tool:<name> (also matches `always`)
        verdict = await fire_hooks(
            f"on_tool:{tool_name}",
            run_id,
            step_ref[0],
            aep_hooks,
            hook_stdin,
            call_id=call_id,
        )
        if verdict == "stop":
            stop_flag[0] = True

        return {}

    async def post_tool_use_failure(
        input_data: dict, tool_use_id: str | None, ctx: Any
    ) -> dict:
        call_id = tool_use_id or "unknown"
        call_timers.pop(call_id, None)
        emit(
            {
                "type": "tool_call_failed",
                "run_id": run_id,
                "step": step_ref[0],
                "call_id": call_id,
                "tool": input_data.get("tool_name", "unknown"),
                "error": str(input_data.get("error", "unknown error")),
                "ts": _now(),
            }
        )
        return {}

    from claude_agent_sdk import HookMatcher

    return {
        "PreToolUse": [HookMatcher(hooks=[pre_tool_use])],
        "PostToolUse": [HookMatcher(hooks=[post_tool_use])],
        "PostToolUseFailure": [HookMatcher(hooks=[post_tool_use_failure])],
    }


def _extract_output(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # Bash tool: {"stdout": "...", "stderr": "..."}
        if "stdout" in raw:
            parts = [raw["stdout"]]
            if raw.get("stderr"):
                parts.append(raw["stderr"])
            return "\n".join(p for p in parts if p)
        # MCP content array: {"content": [{"type": "text", "text": "..."}]}
        content = raw.get("content", [])
        if isinstance(content, list):
            parts = [
                c.get("text", "") if isinstance(c, dict) else str(c) for c in content
            ]
            return "\n".join(p for p in parts if p)
        return str(raw.get("output", raw.get("result", raw)))
    if hasattr(raw, "content"):
        return _extract_output({"content": raw.content})
    return str(raw)
