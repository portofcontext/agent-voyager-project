"""ATIF wire models and document IO, using Harbor's pinned reference models."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from avp._files import atomic_write, local_path, write_document
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
from avp.agent_start import AgentStart
from avp.commission import Commission
from avp.descriptor import AgentDescriptor


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


def avp_metadata(value: Trajectory | Step | ToolCall | ObservationResult) -> dict[str, Any]:
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


@dataclass(frozen=True)
class Recording:
    """A snapshot of the current ATIF document and referenced file bytes."""

    trajectory: Trajectory
    assets: dict[str, bytes] = field(default_factory=dict)
    commission: Commission | None = None
    descriptor: AgentDescriptor | None = None
    agent_start: AgentStart | None = None

    def write(self, path: Path) -> None:
        """Publish referenced files before Agent Start and the ATIF snapshot."""
        if path.name in {"commission.json", "descriptor.json", "agent-start.json"}:
            raise ValueError("trajectory path conflicts with a run document")
        path.parent.mkdir(parents=True, exist_ok=True)
        for name, document in (
            ("commission.json", self.commission),
            ("descriptor.json", self.descriptor),
        ):
            if document is not None:
                write_document(path.parent, name, document)
        for name, content in self.assets.items():
            target = local_path(path.parent, name)
            if target.resolve() == path.resolve():
                raise ValueError("a referenced file cannot replace the trajectory")
            if not target.exists():
                atomic_write(target, content)
            elif target.read_bytes() != content:
                raise ValueError(f"referenced file already exists with different content: {name}")
        if self.agent_start is not None:
            write_document(path.parent, "agent-start.json", self.agent_start)
        atomic_write(
            path, (self.trajectory.model_dump_json(exclude_none=True, indent=2) + "\n").encode()
        )
