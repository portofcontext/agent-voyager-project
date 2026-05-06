"""Pluggable driver protocols for the reference AEP runner (v0.1).

Four drivers:

- ModelDriver       — produces the next ModelResponse given conversation history.
- ToolDriver        — executes locally-handled (non-RPC) tools.
- SupervisorDriver  — handles tool_exec RPC interactions.
- SubagentDriver    — executes declared subagent invocations (sub-loop).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    from aep.enums import StopReason
    from aep.types import RunStateSnapshot, Subagent

# ── Model driver ──────────────────────────────────────────────────────────────


@dataclass
class ScriptedToolCall:
    call_id: str
    tool: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    tokens_input: int
    tokens_output: int
    cost_usd: float
    duration_ms: int
    text: str | None = None
    tool_calls: list[ScriptedToolCall] = field(default_factory=list)
    tokens_cache_read: int | None = None
    tokens_cache_write: int | None = None
    tokens_reasoning_output: int | None = None
    converged: bool = False
    # Streaming observability (OpenTelemetry GenAI conventions). Drivers SHOULD
    # populate these when the underlying API call streamed tokens; non-streaming
    # drivers leave them at None.
    streamed: bool | None = None
    time_to_first_chunk_s: float | None = None
    response_model: str | None = None
    finish_reasons: list[str] | None = None


class ModelDriver(Protocol):
    def step(self, history: list[dict[str, Any]]) -> ModelResponse: ...


# ── Tool driver ───────────────────────────────────────────────────────────────


@dataclass
class ToolOutcome:
    output: str | None = None
    output_json: Any | None = None
    error: str | None = None
    duration_ms: int = 1
    rejected: bool = False
    rejection_reason: str | None = None


class ToolDriver(Protocol):
    def is_local(self, tool: str) -> bool: ...
    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome: ...


# ── Supervisor driver (RPC channel) ──────────────────────────────────────────


class SupervisorDriver(Protocol):
    """Handles tool_exec RPC replies for the runner.

    v0.1: only one RPC kind (tool_exec). No unsolicited messages, no hook responses.
    """

    def observe(self, event: BaseModel) -> None:
        """Called for every runner-emitted event (allows scripted supervisors to react)."""
        ...

    def get_tool_exec_response(self, request_id: str, timeout_ms: int) -> BaseModel | None: ...


# ── Subagent driver ──────────────────────────────────────────────────────────


@dataclass
class SubagentOutcome:
    """Result of running one subagent invocation.

    `text` is the model-visible result returned to the parent (always set —
    becomes the parent's `tool_result`-equivalent). `structured` is optional;
    populated if the subagent's `output_schema` validates a structured result.
    `usage` is the subagent's own consumption rollup; the runner reflects it
    in the parent's cumulative state on `subagent_returned.data.aep.subagent.usage`.

    `error` and `error_code`, when set, mean the subagent failed and the
    runner SHOULD emit `subagent_failed` instead of `subagent_returned`.
    """

    text: str
    reason: StopReason
    duration_ms: int
    usage: RunStateSnapshot
    structured: Any | None = None
    error: str | None = None
    error_code: str | None = None


class SubagentDriver(Protocol):
    """Provider-specific subagent execution.

    The runner calls `invoke()` when the parent agent invokes a tool whose
    name matches a declared `Config.subagents[*].name`. Implementations run
    the subagent's sub-loop (model + tools + verifiers as declared on the
    Subagent object) and return the result + a usage rollup.

    Implementations MAY emit nested events via `parent_observer` so the
    subagent's internal turns observe as a span tree. Each emitted event's
    `data.parent_span_id` MUST be `parent_frame_span_id` (or descend from
    it) and `data.trace_id` MUST equal `parent_trace_id`. Implementations
    MAY skip nested observability — the parent will still emit
    `subagent_invoked` and `subagent_returned` regardless, so the lifecycle
    is on the wire even when the subagent is opaque to the runner (e.g.,
    when delegating into an external SDK that doesn't surface internals).
    """

    def invoke(
        self,
        subagent: Subagent,
        invocation_input: dict[str, Any],
        *,
        parent_trace_id: str,
        parent_frame_span_id: str,
        parent_observer: Callable[[BaseModel], None],
    ) -> SubagentOutcome: ...
