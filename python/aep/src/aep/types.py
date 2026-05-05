"""Pydantic v2 models for AEP v0.1 wire types (v0.1 model).

Each model corresponds 1:1 to a $def in spec/v0.1/aep.schema.json. The Event and
SupervisorMessage discriminated unions match the schema's oneOf-on-type structure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from aep.enums import (
    BUILT_IN_VERIFIER_TRIGGERS,
    ErrorCode,
    OnFailure,
    Source,
    StopReason,
    VerifierError,
    is_on_tool_trigger,
)

# ── Common helpers ───────────────────────────────────────────────────────────

Iso8601 = str


def now_iso() -> str:
    """ISO 8601 / RFC 3339 timestamp with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


_STRICT = ConfigDict(extra="forbid", populate_by_name=True, ser_json_omit_default=False)
_OPEN = ConfigDict(extra="allow", populate_by_name=True)


# ── Value objects (Config side) ───────────────────────────────────────────────


class Boundary(BaseModel):
    model_config = _STRICT
    max_cost_usd: float | None = Field(default=None, gt=0)
    max_steps: int | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, gt=0)


class Skill(BaseModel):
    model_config = _STRICT
    name: str
    source: str
    config: dict[str, Any] | None = None


class Tool(BaseModel):
    model_config = _STRICT
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    timeout_ms: int = Field(default=30000, gt=0)


class VerifierSourceShell(BaseModel):
    model_config = _STRICT
    shell: str


# v0.1 ships only shell-source verifiers; future versions may add other variants
# and at that point `source` becomes a discriminated union.
VerifierSource = VerifierSourceShell


class Verifier(BaseModel):
    """Declarative deterministic check."""

    model_config = _STRICT
    name: str = Field(min_length=1)
    trigger: str
    source: VerifierSourceShell
    on_failure: OnFailure = OnFailure.continue_
    correction_message: str | None = None
    timeout_ms: int = Field(default=30000, gt=0)

    @field_validator("trigger")
    @classmethod
    def _validate_trigger(cls, v: str) -> str:
        if v in BUILT_IN_VERIFIER_TRIGGERS or is_on_tool_trigger(v):
            return v
        raise ValueError(
            f"verifier trigger {v!r} must be one of "
            f"{sorted(BUILT_IN_VERIFIER_TRIGGERS)} or 'on_tool:<name>'"
        )

    @model_validator(mode="after")
    def _inject_correction_requires_message(self) -> Verifier:
        if self.on_failure == OnFailure.inject_correction and not self.correction_message:
            raise ValueError(
                "Verifier.correction_message is required when on_failure='inject_correction'"
            )
        return self


class RunStateSnapshot(BaseModel):
    model_config = _OPEN
    total_cost_usd: float = Field(ge=0)
    total_tokens: int = Field(ge=0)
    total_turns: int = Field(ge=0)
    tokens_input_total: int | None = Field(default=None, ge=0)
    tokens_output_total: int | None = Field(default=None, ge=0)
    tokens_cache_read_total: int | None = Field(default=None, ge=0)
    tokens_cache_write_total: int | None = Field(default=None, ge=0)
    tools_invoked: dict[str, int] | None = None
    started_at: Iso8601 | None = None
    duration_ms: int | None = Field(default=None, ge=0)


# ── Config ────────────────────────────────────────────────────────────────────


class Config(BaseModel):
    """Supervisor's complete declaration of the agent's environment."""

    model_config = _STRICT

    schema_version: Literal["0.1"]
    run_id: str = Field(min_length=1)

    # Supervisor plane (the environment)
    tools: list[Tool] | None = None
    allowed_tools: list[str] | None = None
    verifiers: list[Verifier] | None = None
    boundary: Boundary | None = None
    output_schema: dict[str, Any] | None = None

    # Runner plane (what the agent runs)
    prompt: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    skills: list[Skill] | None = None

    # Metadata
    thread_id: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None


# ── Event base ───────────────────────────────────────────────────────────────


class _EventBase(BaseModel):
    model_config = _STRICT
    run_id: str = Field(min_length=1)
    correlation_id: str | None = Field(default=None, min_length=1)
    ts: Iso8601 = Field(default_factory=now_iso)
    extensions: dict[str, Any] | None = None


# ── Runner-emitted events ────────────────────────────────────────────────────


class _ToolDecl(BaseModel):
    model_config = _OPEN
    name: str
    description: str
    input_schema: dict[str, Any] | None = None


class AgentStartedEvent(_EventBase):
    type: Literal["agent_started"] = "agent_started"
    source: Literal[Source.runner] = Source.runner
    schema_version: Literal["0.1"] = "0.1"
    model: str
    prompt: str | None = None
    system_prompt: str | None = None
    tools: list[_ToolDecl] | None = None
    skills: list[str] | None = None
    thread_id: str | None = None
    session_id: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None


class AgentStoppedEvent(_EventBase):
    type: Literal["agent_stopped"] = "agent_stopped"
    source: Literal[Source.runner] = Source.runner
    reason: StopReason
    state: RunStateSnapshot
    total_tokens: int | None = Field(default=None, ge=0)
    total_cost_usd: float | None = Field(default=None, ge=0)
    total_turns: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    output: Any | None = None


class ModelTurnStartedEvent(_EventBase):
    type: Literal["model_turn_started"] = "model_turn_started"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    context_messages: int | None = Field(default=None, ge=0)


class ModelTurnEndedEvent(_EventBase):
    type: Literal["model_turn_ended"] = "model_turn_ended"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    tokens_input: int = Field(ge=0)
    tokens_output: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    duration_ms: int = Field(ge=0)
    tokens_cache_read: int | None = Field(default=None, ge=0)
    tokens_cache_write: int | None = Field(default=None, ge=0)


class ToolInvokedEvent(_EventBase):
    type: Literal["tool_invoked"] = "tool_invoked"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    call_id: str = Field(min_length=1)
    tool: str
    subtype: str | None = None
    input: dict[str, Any]


class ToolReturnedEvent(_EventBase):
    type: Literal["tool_returned"] = "tool_returned"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    call_id: str = Field(min_length=1)
    tool: str
    output: str
    output_json: Any | None = None
    duration_ms: int = Field(ge=0)
    rejected: bool | None = None
    rejection_reason: str | None = None


class ToolFailedEvent(_EventBase):
    type: Literal["tool_failed"] = "tool_failed"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    call_id: str = Field(min_length=1)
    tool: str
    error: str


class TextEmittedEvent(_EventBase):
    type: Literal["text_emitted"] = "text_emitted"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    text: str


class CostRecordedEvent(_EventBase):
    type: Literal["cost_recorded"] = "cost_recorded"
    source: Literal[Source.runner] = Source.runner
    state: RunStateSnapshot


class SkillLoadedEvent(_EventBase):
    type: Literal["skill_loaded"] = "skill_loaded"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    name: str
    skill_source: str | None = None


class SkillExecutedEvent(_EventBase):
    type: Literal["skill_executed"] = "skill_executed"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    name: str


class ErrorOccurredEvent(_EventBase):
    type: Literal["error_occurred"] = "error_occurred"
    source: Literal[Source.runner] = Source.runner  # v0.1: runner-only
    code: ErrorCode
    message: str


class ToolExecRequestEvent(_EventBase):
    """Agent calling an environmental service to execute a Config-declared tool."""

    type: Literal["tool_exec_request"] = "tool_exec_request"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    request_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    tool: str
    input: dict[str, Any]
    timeout_ms: int = Field(gt=0)


class ToolExecResolvedEvent(_EventBase):
    """Service's reply to a tool_exec_request. Recorded into trajectory verbatim."""

    type: Literal["tool_exec_resolved"] = "tool_exec_resolved"
    source: Literal[Source.supervisor] = Source.supervisor
    request_id: str = Field(min_length=1)
    output: str
    output_json: Any | None = None
    error: str | None = None


class ToolExecTimedOutEvent(_EventBase):
    type: Literal["tool_exec_timed_out"] = "tool_exec_timed_out"
    source: Literal[Source.runner] = Source.runner
    step: int = Field(ge=0)
    request_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    tool: str


class VerifierEvaluatedEvent(_EventBase):
    """A deterministic pass/fail signal recorded by the agent. v0.1: runner-emitted only.

    `error` distinguishes environment failures (script missing, timed out,
    crashed) from genuine rule failures. When `error` is set, `passed` MUST
    be false. When `error` is null, a `passed: false` is a legitimate
    rule-level failure that the agent's logic produced.
    """

    type: Literal["verifier_evaluated"] = "verifier_evaluated"
    source: Literal[Source.runner] = Source.runner  # v0.1: runner-only
    name: str = Field(min_length=1)
    passed: bool
    step: int | None = Field(default=None, ge=0)
    subject_call_ids: list[str] | None = None
    subject_request_ids: list[str] | None = None
    error: VerifierError | None = None
    data: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _error_implies_failed(self) -> VerifierEvaluatedEvent:
        if self.error is not None and self.passed:
            raise ValueError("VerifierEvaluatedEvent.error set but passed=True; mutually exclusive")
        return self


# ── Discriminated unions ─────────────────────────────────────────────────────


_RUNNER_EVENT_TYPES = (
    AgentStartedEvent,
    AgentStoppedEvent,
    ModelTurnStartedEvent,
    ModelTurnEndedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    ToolFailedEvent,
    TextEmittedEvent,
    CostRecordedEvent,
    SkillLoadedEvent,
    SkillExecutedEvent,
    ErrorOccurredEvent,
    ToolExecRequestEvent,
    ToolExecTimedOutEvent,
    VerifierEvaluatedEvent,
)

# v0.1: only RPC replies cross the supervisor channel.
_SUPERVISOR_EVENT_TYPES = (ToolExecResolvedEvent,)

Event = Annotated[
    AgentStartedEvent
    | AgentStoppedEvent
    | ModelTurnStartedEvent
    | ModelTurnEndedEvent
    | ToolInvokedEvent
    | ToolReturnedEvent
    | ToolFailedEvent
    | TextEmittedEvent
    | CostRecordedEvent
    | SkillLoadedEvent
    | SkillExecutedEvent
    | ErrorOccurredEvent
    | ToolExecRequestEvent
    | ToolExecResolvedEvent
    | ToolExecTimedOutEvent
    | VerifierEvaluatedEvent,
    Field(discriminator="type"),
]

SupervisorMessage = ToolExecResolvedEvent

_TYPE_TO_MODEL: dict[str, type[BaseModel]] = {}
for _cls in _RUNNER_EVENT_TYPES + _SUPERVISOR_EVENT_TYPES:
    _TYPE_TO_MODEL[_cls.model_fields["type"].default] = _cls


def parse_event(payload: dict[str, Any]) -> BaseModel | dict[str, Any]:
    """Parse a runner-emitted event payload."""
    t = payload.get("type")
    if not isinstance(t, str):
        raise ValueError("event payload missing required 'type' string")
    cls = _TYPE_TO_MODEL.get(t)
    if cls is None:
        for required in ("type", "source", "run_id", "ts"):
            if required not in payload:
                raise ValueError(f"custom event missing required EventBase field {required!r}")
        return dict(payload)
    return cls.model_validate(payload)


def parse_supervisor_message(payload: dict[str, Any]) -> BaseModel:
    """Parse a supervisor-emitted message. Only RPC replies are valid in v0.1."""
    t = payload.get("type")
    cls = _TYPE_TO_MODEL.get(t) if isinstance(t, str) else None
    if cls is None or cls not in _SUPERVISOR_EVENT_TYPES:
        valid = sorted(c.model_fields["type"].default for c in _SUPERVISOR_EVENT_TYPES)
        raise ValueError(
            f"unknown or unsupported supervisor message type {t!r}; expected one of {valid}"
        )
    return cls.model_validate(payload)
