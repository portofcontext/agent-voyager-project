"""Typed `extra` objects for the vendored ATIF models (`spec/v0.1/trajectory.md`).

Each `*AvpExtra` class matches one table in the spec's reference section. The
vendored ATIF models use the `*Extra` classes for their `extra` field, so
`extra.avp` is validated wherever ATIF is read. Every class keeps keys the spec
doesn't list, as readers must.

Import only `avp._base`, `avp.commission`, and `avp.descriptor` here: the
vendored models import this module.
"""

from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, JsonValue

from avp._base import _CONFIG, ObjectSchema
from avp.commission import Commission
from avp.descriptor import AgentDescriptor, McpServer, Skill, Subagent

NonNegativeInt = Annotated[int, Field(ge=0)]

StopReason = Literal["converged", "refused", "error", "interrupted", "abandoned"]
"""Why a run or a subagent stopped."""

ErrorCode = Literal[
    "invalid_commission",
    "mcp_connect_failed",
    "auth_error",
    "rate_limit",
    "context_limit",
    "output_invalid",
    "agent_crash",
    "unknown",
]
"""What kind of error a system step records."""

ERROR_CODES = get_args(ErrorCode)


def _known_code(value: Any) -> Any:
    return value if not isinstance(value, str) or value in ERROR_CODES else "unknown"


ReadErrorCode = Annotated[ErrorCode, BeforeValidator(_known_code, json_schema_input_type=str)]
"""An error code, read as `unknown` when this version doesn't define it."""

CostSource = Literal["reported", "computed"]
"""Where a response's `cost_usd` comes from."""


class _Open(BaseModel):
    """An `extra.avp` object. Keeps keys the spec doesn't list."""

    model_config = ConfigDict(**_CONFIG, extra="allow")


# Shared types


class Citation(_Open):
    """A source the model cited. Keeps fields the service added."""

    type: str
    """The kind of citation, as the model service names it, such as `url_citation`."""
    cited_text: str | None = None
    """The text cited."""
    start_index: NonNegativeInt | None = None
    """Where the cited part of the text starts."""
    end_index: NonNegativeInt | None = None
    """Where it ends."""
    source_id: str | None = None
    """The service's ID for the source."""
    source_url: str | None = None
    """The source's URL."""
    source_title: str | None = None
    """The source's title."""


class ContentMetadata(_Open):
    """Data for one part of a step's `message` or a result's `content`."""

    part_index: NonNegativeInt
    """The position of the part in `message` or `content`, from 0. `0` when the value is a string."""
    citations: list[Citation] | None = None
    """Sources the model cited in the part."""
    refusal: bool | None = None
    """`true` when the part is the model's text declining the task."""


class ReasoningMetadata(_Open):
    """Data for one block of the model's reasoning. Keeps fields the service added."""

    start: NonNegativeInt | None = None
    """Where the block's text starts in `reasoning_content`."""
    end: NonNegativeInt | None = None
    """Where it ends. When `start` and `end` are absent, the block is all of `reasoning_content`."""
    signature: str | None = None
    """The service's token for passing the reasoning back to it."""
    encrypted_content: str | None = None
    """The service's encrypted reasoning, when it returned the block encrypted."""


class AgentModel(_Open):
    """The service that runs the model in `agent.model_name`."""

    provider: str
    """The service that runs the model."""
    base_url: str | None = None
    """The URL of the service's API. Absent means the service's default."""


class AgentTool(_Open):
    """The Tool fields that ATIF's OpenAI-style tool definition can't hold."""

    title: str | None = None
    """The tool's display name."""
    output_schema: ObjectSchema | None = Field(default=None, alias="outputSchema")
    """The shape of the tool's structured result."""
    annotations: dict[str, JsonValue] | None = None
    """The tool's MCP annotations."""
    mcp_server_id: str | None = None
    """The `id` of the MCP server in `mcp_servers` the tool comes from."""


# One `extra.avp` object per ATIF object


class TrajectoryAvpExtra(_Open):
    """At the trajectory's `extra.avp`, and on each embedded subagent trajectory."""

    avp_version: Literal["0.1"]
    """The AVP version the Trajectory follows."""
    commission: Commission | JsonValue = None
    """The Commission exactly as the agent received it. Raw JSON or text when it isn't valid."""
    started_at: str | None = None
    """When the run started, as an RFC 3339 timestamp."""
    stopped_at: str
    """When the run stopped, as an RFC 3339 timestamp."""
    stop_reason: StopReason
    """Why the run stopped."""
    output: JsonValue = None
    """The run's result, when it differs from the last agent message. Set
    explicitly to `null` when the run returned no result."""


class AgentAvpExtra(_Open):
    """At `agent.extra.avp`: what the run used."""

    descriptor: AgentDescriptor | None = None
    """The agent's Descriptor, unchanged. Absent on subagent trajectories."""
    model: AgentModel | None = None
    """The service that runs the model in `agent.model_name`."""
    tools: dict[str, AgentTool] | None = None
    """For each tool in `agent.tool_definitions`, keyed by its name."""
    mcp_servers: list[McpServer] | None = None
    """The MCP servers the run used, with their `status`."""
    skills: list[Skill] | None = None
    """The skills the run used. `source` points to the saved skill directory."""
    subagents: list[Subagent] | None = None
    """The subagents available to the run."""


class StepAvpExtra(_Open):
    """At `steps[].extra.avp`."""

    duration_ms: NonNegativeInt | None = None
    """How long the model response took, in milliseconds."""
    finish_reasons: list[str] | None = None
    """Why the model stopped, exactly as the service reported it."""
    message_metadata: list[ContentMetadata] | None = None
    """Data for parts of `message`."""
    reasoning_metadata: list[ReasoningMetadata] | None = None
    """Data for blocks of the model's reasoning."""
    error_code: ReadErrorCode | None = None
    """What kind of error a system step records."""


class ToolCallAvpExtra(_Open):
    """At `steps[].tool_calls[].extra.avp`."""

    server_side: bool | None = None
    """`true` when the model service ran the tool, not the agent."""


class ObservationResultAvpExtra(_Open):
    """At `steps[].observation.results[].extra.avp`."""

    duration_ms: NonNegativeInt | None = None
    """How long the tool took, in milliseconds, ending at `finished_at`."""
    finished_at: str | None = None
    """When the result arrived, as an RFC 3339 timestamp."""
    is_error: bool | None = None
    """`true` when the call failed."""
    structured_content: JsonValue = None
    """A result meant for programs, given beside `content`."""
    content_metadata: list[ContentMetadata] | None = None
    """Data for parts of `content`."""


class MetricsAvpExtra(_Open):
    """At `steps[].metrics.extra.avp`: the usage of one model response."""

    cache_creation_input_tokens: NonNegativeInt | None = None
    """The input tokens written to the cache. Included in `prompt_tokens`."""
    reasoning_output_tokens: NonNegativeInt | None = None
    """The output tokens the model spent on reasoning. Included in `completion_tokens`."""
    cost_source: CostSource | None = None
    """Where `cost_usd` comes from."""


class FinalMetricsAvpExtra(_Open):
    """At `final_metrics.extra.avp`."""

    total_cache_creation_input_tokens: NonNegativeInt | None = None
    """The total of `cache_creation_input_tokens`."""
    total_reasoning_output_tokens: NonNegativeInt | None = None
    """The total of `reasoning_output_tokens`."""
    total_responses: NonNegativeInt | None = None
    """How many model responses were made."""
    cost_complete: bool | None = None
    """`false` when `total_cost_usd` leaves out responses whose cost is unknown."""


# The `extra` objects


class Extra(BaseModel):
    """An ATIF `extra` object. Keeps keys beside `avp`, and reads like a dict."""

    model_config = ConfigDict(extra="allow")

    def __getitem__(self, key: str) -> Any:
        if key in type(self).model_fields:
            value = getattr(self, key)
            if value is None and key not in self.model_fields_set:
                raise KeyError(key)
            return value
        return (self.model_extra or {})[key]

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.get(key, _MISSING) is not _MISSING


_MISSING = object()


class TrajectoryExtra(Extra):
    avp: TrajectoryAvpExtra | None = None


class AgentExtra(Extra):
    avp: AgentAvpExtra | None = None


class StepExtra(Extra):
    avp: StepAvpExtra | None = None


class ToolCallExtra(Extra):
    avp: ToolCallAvpExtra | None = None


class ObservationResultExtra(Extra):
    avp: ObservationResultAvpExtra | None = None


class MetricsExtra(Extra):
    avp: MetricsAvpExtra | None = None


class FinalMetricsExtra(Extra):
    avp: FinalMetricsAvpExtra | None = None


EXTRAS: dict[str, type[Extra]] = {
    "Trajectory": TrajectoryExtra,
    "Agent": AgentExtra,
    "Step": StepExtra,
    "ToolCall": ToolCallExtra,
    "ObservationResult": ObservationResultExtra,
    "Metrics": MetricsExtra,
    "FinalMetrics": FinalMetricsExtra,
    "SubagentTrajectoryRef": Extra,
}
"""The `extra` class for each vendored ATIF model that has an `extra` field."""
