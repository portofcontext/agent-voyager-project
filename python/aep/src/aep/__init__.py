"""aep — Python reference implementation for Agent Execution Protocol (v0.1 model)."""

from aep.enums import (
    BUILT_IN_VERIFIER_TRIGGERS,
    ErrorCode,
    OnFailure,
    Source,
    StopReason,
    is_on_tool_trigger,
)
from aep.io import (
    iter_events,
    read_supervisor_message,
    write_event,
)
from aep.types import (
    # Runner-emitted events
    AgentStartedEvent,
    AgentStoppedEvent,
    Boundary,
    # Config + value objects
    Config,
    CostRecordedEvent,
    ErrorOccurredEvent,
    # Unions / parsing
    Event,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    RunStateSnapshot,
    Skill,
    SkillExecutedEvent,
    SkillLoadedEvent,
    SupervisorMessage,
    TextEmittedEvent,
    Tool,
    ToolExecRequestEvent,
    # Supervisor RPC replies
    ToolExecResolvedEvent,
    ToolExecTimedOutEvent,
    ToolFailedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    Verifier,
    VerifierEvaluatedEvent,
    VerifierSourceShell,
    parse_event,
    parse_supervisor_message,
)

__version__ = "0.1.0"
SCHEMA_VERSION = "0.1"

__all__ = [
    "BUILT_IN_VERIFIER_TRIGGERS",
    "SCHEMA_VERSION",
    # Runner events
    "AgentStartedEvent",
    "AgentStoppedEvent",
    "Boundary",
    # Config
    "Config",
    "CostRecordedEvent",
    "ErrorCode",
    "ErrorOccurredEvent",
    # Unions / parsing
    "Event",
    "ModelTurnEndedEvent",
    "ModelTurnStartedEvent",
    "OnFailure",
    "RunStateSnapshot",
    "Skill",
    "SkillExecutedEvent",
    "SkillLoadedEvent",
    # Enums
    "Source",
    "StopReason",
    "SupervisorMessage",
    "TextEmittedEvent",
    "Tool",
    "ToolExecRequestEvent",
    # Supervisor RPC replies
    "ToolExecResolvedEvent",
    "ToolExecTimedOutEvent",
    "ToolFailedEvent",
    "ToolInvokedEvent",
    "ToolReturnedEvent",
    "Verifier",
    "VerifierEvaluatedEvent",
    "VerifierSourceShell",
    "__version__",
    "is_on_tool_trigger",
    "iter_events",
    "parse_event",
    "parse_supervisor_message",
    "read_supervisor_message",
    # IO
    "write_event",
]
