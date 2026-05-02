"""Pluggable driver protocols for the reference AEP runner (v0.1).

Three drivers:

- ModelDriver       — produces the next ModelResponse given conversation history.
- ToolDriver        — executes locally-handled (non-RPC) tools.
- SupervisorDriver  — handles RPC interactions (tool_exec, re_observation supervisor-source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

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
    converged: bool = False


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
    """Handles RPC replies for the runner.

    v0.1: only two RPC kinds. No unsolicited messages, no hook responses.
    """

    def observe(self, event: BaseModel) -> None:
        """Called for every runner-emitted event (allows scripted supervisors to react)."""
        ...

    def get_tool_exec_response(self, request_id: str, timeout_ms: int) -> BaseModel | None: ...

    def get_re_observation_response(self, request_id: str, timeout_ms: int) -> BaseModel | None: ...
