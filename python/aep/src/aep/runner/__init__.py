"""Reference AEP runner — implements SPEC.md §10.3 over pluggable drivers."""

from aep.runner.boundary import (
    check_consumption,
    check_step_projection,
)
from aep.runner.drivers import (
    ModelDriver,
    ModelResponse,
    ScriptedToolCall,
    SupervisorDriver,
    ToolDriver,
    ToolOutcome,
)
from aep.runner.runner import AEPRunner

__all__ = [
    "AEPRunner",
    "ModelDriver",
    "ModelResponse",
    "ScriptedToolCall",
    "SupervisorDriver",
    "ToolDriver",
    "ToolOutcome",
    "check_consumption",
    "check_step_projection",
]
