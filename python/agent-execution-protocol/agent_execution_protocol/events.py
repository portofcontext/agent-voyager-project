"""AEP event types and stdout emitters.

Two APIs:
  1. Typed dataclasses — for constructing and inspecting events programmatically
  2. emit_*() functions — for quickly writing events to stdout as NDJSON
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def emit(event: dict[str, Any], file=None) -> None:
    """Write one AEP event as a single NDJSON line, flushing immediately."""
    out = file or sys.stdout
    out.write(json.dumps(event) + "\n")
    out.flush()


# ── Event dataclasses ─────────────────────────────────────────────────────────

@dataclass
class AgentStart:
    type: Literal["agent_start"] = field(default="agent_start", init=False)
    schema_version: str = "0.1"
    run_id: str = ""
    model: str = ""
    prompt: str | None = None
    system_prompt: str | None = None
    tools: list[dict] | None = None
    ts: str = field(default_factory=_now)
    thread_id: str | None = None
    session_id: str | None = None
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "model": self.model,
            "ts": self.ts,
        }
        if self.prompt is not None:
            d["prompt"] = self.prompt
        if self.system_prompt is not None:
            d["system_prompt"] = self.system_prompt
        if self.tools is not None:
            d["tools"] = self.tools
        if self.thread_id is not None:
            d["thread_id"] = self.thread_id
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.tags:
            d["tags"] = self.tags
        if self.meta:
            d["meta"] = self.meta
        return d


@dataclass
class ModelTurnStart:
    type: Literal["model_turn_start"] = field(default="model_turn_start", init=False)
    run_id: str = ""
    step: int = 0
    ts: str = field(default_factory=_now)
    context_messages: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type, "run_id": self.run_id, "step": self.step, "ts": self.ts}
        if self.context_messages is not None:
            d["context_messages"] = self.context_messages
        return d


@dataclass
class ModelTurnEnd:
    type: Literal["model_turn_end"] = field(default="model_turn_end", init=False)
    run_id: str = ""
    step: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    tokens_cache_read: int | None = None
    tokens_cache_write: int | None = None
    ts: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "run_id": self.run_id,
            "step": self.step,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
            "ts": self.ts,
        }
        if self.tokens_cache_read is not None:
            d["tokens_cache_read"] = self.tokens_cache_read
        if self.tokens_cache_write is not None:
            d["tokens_cache_write"] = self.tokens_cache_write
        return d


@dataclass
class ToolCall:
    type: Literal["tool_call"] = field(default="tool_call", init=False)
    run_id: str = ""
    step: int = 0
    call_id: str = ""
    tool: str = ""
    input: Any = field(default_factory=dict)
    ts: str = field(default_factory=_now)
    subtype: str | None = None  # "shell" | "function" | "retrieval" | "embedding" | "mcp"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "run_id": self.run_id,
            "step": self.step,
            "call_id": self.call_id,
            "tool": self.tool,
            "input": self.input,
            "ts": self.ts,
        }
        if self.subtype is not None:
            d["subtype"] = self.subtype
        return d


@dataclass
class ToolResult:
    type: Literal["tool_result"] = field(default="tool_result", init=False)
    run_id: str = ""
    step: int = 0
    call_id: str = ""
    tool: str = ""
    output: str = ""
    duration_ms: int = 0
    ts: str = field(default_factory=_now)
    rejected: bool = False
    rejection_reason: str | None = None  # "path_not_in_allow_write" | "ceiling_reached" | "tool_not_allowed"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "run_id": self.run_id,
            "step": self.step,
            "call_id": self.call_id,
            "tool": self.tool,
            "output": self.output,
            "duration_ms": self.duration_ms,
            "ts": self.ts,
        }
        if self.rejected:
            d["rejected"] = True
        if self.rejection_reason is not None:
            d["rejection_reason"] = self.rejection_reason
        return d


@dataclass
class ToolCallFailed:
    type: Literal["tool_call_failed"] = field(default="tool_call_failed", init=False)
    run_id: str = ""
    step: int = 0
    call_id: str = ""
    tool: str = ""
    error: str = ""
    ts: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "run_id": self.run_id,
            "step": self.step,
            "call_id": self.call_id,
            "tool": self.tool,
            "error": self.error,
            "ts": self.ts,
        }


@dataclass
class TextOutput:
    type: Literal["text_output"] = field(default="text_output", init=False)
    run_id: str = ""
    step: int = 0
    text: str = ""
    ts: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "run_id": self.run_id, "step": self.step, "text": self.text, "ts": self.ts}


@dataclass
class CostUpdate:
    type: Literal["cost_update"] = field(default="cost_update", init=False)
    run_id: str = ""
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    ts: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "run_id": self.run_id,
            "total_cost_usd": self.total_cost_usd,
            "total_tokens": self.total_tokens,
            "ts": self.ts,
        }


@dataclass
class SkillRead:
    type: Literal["skill_read"] = field(default="skill_read", init=False)
    run_id: str = ""
    step: int = 0
    name: str = ""
    ts: str = field(default_factory=_now)
    source: str | None = None  # path or URL the skill was loaded from

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type, "run_id": self.run_id, "step": self.step,
            "name": self.name, "ts": self.ts,
        }
        if self.source is not None:
            d["source"] = self.source
        return d


@dataclass
class SkillExecute:
    type: Literal["skill_execute"] = field(default="skill_execute", init=False)
    run_id: str = ""
    step: int = 0
    name: str = ""
    ts: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type, "run_id": self.run_id, "step": self.step,
            "name": self.name, "ts": self.ts,
        }


@dataclass
class ContextCompaction:
    type: Literal["context_compaction"] = field(default="context_compaction", init=False)
    run_id: str = ""
    step: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    ts: str = field(default_factory=_now)
    compacted_messages: list[dict] | None = None  # synthetic messages produced by compaction

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "run_id": self.run_id,
            "step": self.step,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "ts": self.ts,
        }
        if self.compacted_messages is not None:
            d["compacted_messages"] = self.compacted_messages
        return d


@dataclass
class RunError:
    type: Literal["error"] = field(default="error", init=False)
    run_id: str = ""
    code: str = "unknown"  # "rate_limit" | "context_limit" | "auth_error" | "runner_crash" | "unknown"
    message: str = ""
    ts: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "run_id": self.run_id, "code": self.code, "message": self.message, "ts": self.ts}


@dataclass
class AgentStop:
    type: Literal["agent_stop"] = field(default="agent_stop", init=False)
    run_id: str = ""
    reason: str = "converged"  # "converged" | "budget_exhausted" | "token_limit" | "turn_limit" | "error" | "interrupted"
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_turns: int = 0
    duration_ms: int = 0
    ts: str = field(default_factory=_now)
    output: Any = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "run_id": self.run_id,
            "reason": self.reason,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "total_turns": self.total_turns,
            "duration_ms": self.duration_ms,
            "ts": self.ts,
        }
        if self.output is not None:
            d["output"] = self.output
        return d


@dataclass
class HookRequest:
    """Emitted by the runner when it pauses at a hook trigger point.

    The runner emits this to stdout and then blocks reading stdin for a
    ``hook_verdict`` response. The supervisor reads this event, runs whatever
    checks it wants, and writes a ``hook_verdict`` back on the runner's stdin.
    """
    type: Literal["hook_request"] = field(default="hook_request", init=False)
    run_id: str = ""
    request_id: str = ""
    hook_name: str = ""
    trigger: str = ""
    step: int = 0
    timeout_ms: int = 30000
    ts: str = field(default_factory=_now)
    call_id: str | None = None   # present when trigger is on_tool:<name>
    context: dict[str, Any] | None = None  # snapshot of triggering event context

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "hook_name": self.hook_name,
            "trigger": self.trigger,
            "step": self.step,
            "timeout_ms": self.timeout_ms,
            "ts": self.ts,
        }
        if self.call_id is not None:
            d["call_id"] = self.call_id
        if self.context is not None:
            d["context"] = self.context
        return d


@dataclass
class HookVerdict:
    """Sent by the supervisor over stdin in response to a hook_request.

    This message flows supervisor → runner (stdin), not runner → stdout.
    It is included as a dataclass so supervisors have a typed object to
    construct and runners have a typed object after deserializing it.
    """
    type: Literal["hook_verdict"] = field(default="hook_verdict", init=False)
    run_id: str = ""
    request_id: str = ""
    verdict: str = "continue"  # "continue" | "stop" | "inject"
    ts: str = field(default_factory=_now)
    message: str | None = None  # injected user message when verdict == "inject"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "verdict": self.verdict,
            "ts": self.ts,
        }
        if self.message is not None:
            d["message"] = self.message
        return d


@dataclass
class HookVerdictApplied:
    """Emitted by the runner after it receives and acts on a hook_verdict.

    Closes the hook_request/hook_verdict_applied pair in the trajectory,
    making it unambiguous what happened at the hook point and whether the
    verdict came from the supervisor or from a timeout.
    """
    type: Literal["hook_verdict_applied"] = field(default="hook_verdict_applied", init=False)
    run_id: str = ""
    request_id: str = ""
    verdict: str = "continue"  # "continue" | "stop" | "inject"
    ts: str = field(default_factory=_now)
    timed_out: bool = False  # True if default_verdict was applied due to timeout

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "verdict": self.verdict,
            "ts": self.ts,
        }
        if self.timed_out:
            d["timed_out"] = True
        return d


AepEvent = (
    AgentStart
    | ModelTurnStart
    | ModelTurnEnd
    | ToolCall
    | ToolResult
    | ToolCallFailed
    | TextOutput
    | CostUpdate
    | SkillRead
    | SkillExecute
    | ContextCompaction
    | RunError
    | AgentStop
    | HookRequest
    | HookVerdict
    | HookVerdictApplied
)

_EVENT_TYPES = {
    "agent_start": AgentStart,
    "model_turn_start": ModelTurnStart,
    "model_turn_end": ModelTurnEnd,
    "tool_call": ToolCall,
    "tool_result": ToolResult,
    "tool_call_failed": ToolCallFailed,
    "text_output": TextOutput,
    "cost_update": CostUpdate,
    "skill_read": SkillRead,
    "skill_execute": SkillExecute,
    "context_compaction": ContextCompaction,
    "error": RunError,
    "agent_stop": AgentStop,
    "hook_request": HookRequest,
    "hook_verdict": HookVerdict,
    "hook_verdict_applied": HookVerdictApplied,
}

VALID_STOP_REASONS = frozenset({
    "converged", "budget_exhausted", "token_limit", "turn_limit",
    "error", "interrupted", "supervisor_stopped",
})

VALID_ERROR_CODES = frozenset(
    {"rate_limit", "context_limit", "auth_error", "runner_crash", "unknown"}
)

VALID_REJECTION_REASONS = frozenset(
    {"path_not_in_allow_write", "ceiling_reached", "tool_not_allowed"}
)


def event_from_dict(d: dict[str, Any]) -> AepEvent | dict:
    """Deserialize one AEP event dict into the appropriate dataclass.

    For known AEP event types, returns the corresponding dataclass instance.
    For unknown event types (e.g. custom or future event types), returns the
    raw dict unchanged so that custom event types pass through without error.
    """
    event_type = d.get("type")
    cls = _EVENT_TYPES.get(event_type)  # type: ignore[arg-type]
    if cls is None:
        return d
    # Build dataclass from dict, ignoring the literal 'type' field
    init_fields = {k: v for k, v in d.items() if k != "type"}
    try:
        return cls(**init_fields)
    except TypeError as e:
        raise ValueError(f"Failed to construct {cls.__name__} from {d}: {e}") from e


# ── Emit helpers (write to stdout) ────────────────────────────────────────────

def emit_agent_start(
    *,
    run_id: str,
    model: str,
    prompt: str | None = None,
    system_prompt: str | None = None,
    tools: list[dict] | None = None,
    thread_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    file=None,
) -> None:
    e = AgentStart(run_id=run_id, model=model, prompt=prompt, system_prompt=system_prompt,
                   tools=tools, thread_id=thread_id, session_id=session_id,
                   tags=tags or [], meta=meta or {})
    emit(e.to_dict(), file=file)


def emit_model_turn_start(*, run_id: str, step: int, context_messages: int | None = None, file=None) -> None:
    emit(ModelTurnStart(run_id=run_id, step=step, context_messages=context_messages).to_dict(), file=file)


def emit_model_turn_end(
    *, run_id: str, step: int, tokens_input: int, tokens_output: int,
    cost_usd: float, duration_ms: int,
    tokens_cache_read: int | None = None, tokens_cache_write: int | None = None,
    file=None,
) -> None:
    emit(ModelTurnEnd(run_id=run_id, step=step, tokens_input=tokens_input,
                      tokens_output=tokens_output, cost_usd=cost_usd,
                      duration_ms=duration_ms, tokens_cache_read=tokens_cache_read,
                      tokens_cache_write=tokens_cache_write).to_dict(), file=file)


def emit_context_compaction(
    *, run_id: str, step: int, tokens_before: int, tokens_after: int,
    compacted_messages: list[dict] | None = None, file=None,
) -> None:
    emit(ContextCompaction(run_id=run_id, step=step, tokens_before=tokens_before,
                           tokens_after=tokens_after,
                           compacted_messages=compacted_messages).to_dict(), file=file)


def emit_tool_call(
    *, run_id: str, step: int, call_id: str, tool: str, input: Any,
    subtype: str | None = None, file=None,
) -> None:
    emit(ToolCall(run_id=run_id, step=step, call_id=call_id, tool=tool,
                  input=input, subtype=subtype).to_dict(), file=file)


def emit_tool_result(
    *, run_id: str, step: int, call_id: str, tool: str, output: str,
    duration_ms: int, rejected: bool = False, rejection_reason: str | None = None,
    file=None,
) -> None:
    emit(ToolResult(run_id=run_id, step=step, call_id=call_id, tool=tool,
                    output=output, duration_ms=duration_ms, rejected=rejected,
                    rejection_reason=rejection_reason).to_dict(), file=file)


def emit_tool_call_failed(
    *, run_id: str, step: int, call_id: str, tool: str, error: str, file=None,
) -> None:
    emit(ToolCallFailed(run_id=run_id, step=step, call_id=call_id, tool=tool,
                        error=error).to_dict(), file=file)


def emit_text_output(*, run_id: str, step: int, text: str, file=None) -> None:
    emit(TextOutput(run_id=run_id, step=step, text=text).to_dict(), file=file)


def emit_cost_update(
    *, run_id: str, total_cost_usd: float, total_tokens: int, file=None,
) -> None:
    emit(CostUpdate(run_id=run_id, total_cost_usd=total_cost_usd,
                    total_tokens=total_tokens).to_dict(), file=file)


def emit_error(*, run_id: str, code: str, message: str, file=None) -> None:
    emit(RunError(run_id=run_id, code=code, message=message).to_dict(), file=file)


def emit_agent_stop(
    *, run_id: str, reason: str, total_tokens: int, total_cost_usd: float,
    total_turns: int, duration_ms: int, output: Any = None, file=None,
) -> None:
    emit(AgentStop(run_id=run_id, reason=reason, total_tokens=total_tokens,
                   total_cost_usd=total_cost_usd, total_turns=total_turns,
                   duration_ms=duration_ms, output=output).to_dict(), file=file)


def emit_skill_read(*, run_id: str, step: int, name: str, source: str | None = None, file=None) -> None:
    emit(SkillRead(run_id=run_id, step=step, name=name, source=source).to_dict(), file=file)


def emit_skill_execute(*, run_id: str, step: int, name: str, file=None) -> None:
    emit(SkillExecute(run_id=run_id, step=step, name=name).to_dict(), file=file)


def emit_hook_request(
    *, run_id: str, request_id: str, hook_name: str, trigger: str, step: int,
    timeout_ms: int = 30000, call_id: str | None = None,
    context: dict[str, Any] | None = None, file=None,
) -> None:
    emit(HookRequest(run_id=run_id, request_id=request_id, hook_name=hook_name,
                     trigger=trigger, step=step, timeout_ms=timeout_ms,
                     call_id=call_id, context=context).to_dict(), file=file)


def emit_hook_verdict_applied(
    *, run_id: str, request_id: str, verdict: str, timed_out: bool = False, file=None,
) -> None:
    emit(HookVerdictApplied(run_id=run_id, request_id=request_id,
                            verdict=verdict, timed_out=timed_out).to_dict(), file=file)
