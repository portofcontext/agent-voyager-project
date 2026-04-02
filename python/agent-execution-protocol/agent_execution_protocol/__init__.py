"""agent-execution-protocol — open standard for agent observability.

Core types:
    AepConfig       — config passed to a runner on stdin
    AepBoundary     — execution limits the runner enforces
    AepHook         — supervisor hook declared in config
    AepEvent        — union of all event dataclasses
    AgentStart, ModelTurnStart, ModelTurnEnd, ToolCall, ToolResult,
    ToolCallFailed, TextOutput, CostUpdate, SkillRead, SkillExecute,
    ContextCompaction, RunError, AgentStop,
    HookRequest, HookVerdict, HookVerdictApplied

Emit helpers (write to stdout as NDJSON):
    emit_agent_start, emit_model_turn_start, emit_model_turn_end,
    emit_tool_call, emit_tool_result, emit_tool_call_failed,
    emit_text_output, emit_cost_update, emit_context_compaction,
    emit_skill_read, emit_skill_execute,
    emit_error, emit_agent_stop,
    emit_hook_request, emit_hook_verdict_applied

Stream utilities:
    write_event(event)         — serialize one event to a file
    read_config(file)          — read AEP config JSON from stdin
    read_verdict(file)         — read a hook_verdict from stdin (runner-side)
    send_verdict(verdict, file) — write a hook_verdict to a file (supervisor-side)
    parse_stream(text)         — parse NDJSON text → (events, errors)
    iter_stream(file)          — iterate NDJSON file line by line

Validation:
    validate(events)        — returns list[Violation]
    Violation               — code, message, event_index
"""

from .config import AepConfig, AepBoundary, AepHook
from .events import (
    AepEvent,
    AgentStart,
    ModelTurnStart,
    ModelTurnEnd,
    ToolCall,
    ToolResult,
    ToolCallFailed,
    TextOutput,
    CostUpdate,
    ContextCompaction,
    RunError,
    AgentStop,
    SkillRead,
    SkillExecute,
    HookRequest,
    HookVerdict,
    HookVerdictApplied,
    emit,
    emit_agent_start,
    emit_model_turn_start,
    emit_model_turn_end,
    emit_tool_call,
    emit_tool_result,
    emit_tool_call_failed,
    emit_text_output,
    emit_cost_update,
    emit_context_compaction,
    emit_skill_read,
    emit_skill_execute,
    emit_error,
    emit_agent_stop,
    emit_hook_request,
    emit_hook_verdict_applied,
    event_from_dict,
)
from .stream import write_event, read_config, read_verdict, send_verdict, parse_stream, iter_stream
from .validate import validate, Violation

__all__ = [
    # Config
    "AepConfig", "AepBoundary", "AepHook",
    # Event types
    "AepEvent", "AgentStart", "ModelTurnStart", "ModelTurnEnd",
    "ToolCall", "ToolResult", "ToolCallFailed", "TextOutput",
    "CostUpdate", "SkillRead", "SkillExecute", "ContextCompaction", "RunError", "AgentStop",
    "HookRequest", "HookVerdict", "HookVerdictApplied",
    # Emit helpers
    "emit", "emit_agent_start", "emit_model_turn_start", "emit_model_turn_end",
    "emit_tool_call", "emit_tool_result", "emit_tool_call_failed",
    "emit_text_output", "emit_cost_update", "emit_context_compaction",
    "emit_skill_read", "emit_skill_execute",
    "emit_error", "emit_agent_stop",
    "emit_hook_request", "emit_hook_verdict_applied",
    # Stream
    "write_event", "read_config", "read_verdict", "send_verdict",
    "parse_stream", "iter_stream", "event_from_dict",
    # Validation
    "validate", "Violation",
]
