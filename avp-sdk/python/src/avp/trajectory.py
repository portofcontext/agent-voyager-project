"""ATIF models with AVP's typed extras, and document IO (`spec/v0.1/trajectory.md`)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from avp._files import atomic_write, local_path
from avp._trajectory_extra import (  # noqa: F401
    AgentAvpExtra,
    AgentExtra,
    AgentModel,
    AgentTool,
    Citation,
    ContentMetadata,
    CostSource,
    ErrorCode,
    Extra,
    FinalMetricsAvpExtra,
    FinalMetricsExtra,
    MetricsAvpExtra,
    MetricsExtra,
    ObservationResultAvpExtra,
    ObservationResultExtra,
    ReasoningMetadata,
    StepAvpExtra,
    StepExtra,
    StopReason,
    ToolCallAvpExtra,
    ToolCallExtra,
    TrajectoryAvpExtra,
    TrajectoryExtra,
)
from avp._vendor.atif import (  # noqa: F401
    Agent,
    ContentPart,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    SubagentTrajectoryRef,
    ToolCall,
    Trajectory,
)
from avp.descriptor import Tool


def parse_trajectory(value: dict[str, Any] | str | bytes) -> Trajectory:
    """Read any supported upstream ATIF document, including non-AVP producers."""
    if isinstance(value, dict):
        return Trajectory.model_validate(value)
    return Trajectory.model_validate_json(value)


def documents(trajectory: Trajectory):
    """Walk a document and its embedded descendants once."""
    yield trajectory
    for child in trajectory.subagent_trajectories or []:
        yield from documents(child)


def avp_metadata(
    value: Trajectory | Agent | Step | ToolCall | ObservationResult,
) -> dict[str, Any]:
    """The object's `extra.avp` as JSON, or `{}` when it has none, as plain ATIF may not."""
    avp = value.extra.avp if value.extra is not None else None
    return avp.model_dump(mode="json", by_alias=True, exclude_unset=True) if avp else {}


def final_output(trajectory: Trajectory) -> Any:
    """Returned value, falling back to the final root agent message in ATIF."""
    meta = avp_metadata(trajectory)
    if "output" in meta:
        return meta["output"]
    for step in reversed(trajectory.steps):
        if step.source == "agent":
            return (
                step.message
                if isinstance(step.message, str)
                else [part.model_dump(mode="json", exclude_none=True) for part in step.message]
            )
    return None


def tool_definitions(tools: list[Tool]) -> tuple[list[dict[str, Any]], dict[str, AgentTool]]:
    """`agent.tool_definitions` and `agent.extra.avp.tools` for MCP-style tools.
    The second holds, by name, the fields the OpenAI function shape can't."""
    definitions, details = [], {}
    for tool in tools:
        function: dict[str, Any] = {"name": tool.name, "parameters": tool.input_schema}
        if tool.description is not None:
            function["description"] = tool.description
        definitions.append({"type": "function", "function": function})
        rest = tool.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            exclude={"name", "description", "input_schema"},
        )
        if rest:
            details[tool.name] = AgentTool.model_validate(rest)
    return definitions, details


@dataclass(frozen=True)
class Recording:
    """A finished ATIF document and the files it references, such as images
    and skill directories, by path relative to the document."""

    trajectory: Trajectory
    assets: dict[str, bytes] = field(default_factory=dict)

    def json(self, *, indent: int | None = None) -> str:
        return self.trajectory.model_dump_json(by_alias=True, exclude_unset=True, indent=indent)

    def write(self, path: Path) -> None:
        """Write the referenced files, then the document."""
        path.parent.mkdir(parents=True, exist_ok=True)
        for name, content in self.assets.items():
            target = local_path(path.parent, name)
            if target.resolve() == path.resolve():
                raise ValueError("a referenced file cannot replace the trajectory")
            if not target.exists():
                atomic_write(target, content)
            elif target.read_bytes() != content:
                raise ValueError(f"referenced file already exists with different content: {name}")
        atomic_write(path, (self.json(indent=2) + "\n").encode())
