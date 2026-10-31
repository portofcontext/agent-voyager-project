"""Wire types for the Trajectory spec (`spec/v0.1/trajectory.md`).

Each class matches one table in the spec's reference section. An event's `data`
has its own class, named after the event type: `ToolInvoked` is the `data` of a
`ToolInvokedEvent`.
"""

from typing import Annotated, Any, Literal

from pydantic import (
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from avp._base import OpenWireModel, Timestamp, WireModel
from avp.commission import Commission, ModelRef
from avp.descriptor import AgentDescriptor, McpServer, Skill, Subagent, Tool

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
"""What kind of error an `error_occurred` reports."""

# Content blocks


class Citation(OpenWireModel):
    """A source the model cited for a text block. Keeps fields the service added."""

    type: str
    """The kind of citation, as the model service names it, such as `url_citation`."""
    cited_text: str | None = None
    """The text cited."""
    start_index: NonNegativeInt | None = None
    """Where the cited part of the block's `text` starts."""
    end_index: NonNegativeInt | None = None
    """Where it ends."""
    source_id: str | None = None
    """The service's ID for the source."""
    source_url: str | None = None
    """The source's URL."""
    source_title: str | None = None
    """The source's title."""


class Source(OpenWireModel):
    """Where an image's data is. In v0.1 the data is always inline. Keeps fields the service added."""

    type: Literal["base64"]
    media_type: str
    """The image's media type, such as `image/png`."""
    data: str
    """The image, base64-encoded."""


# A block keeps fields the model service added that AVP doesn't list, such as
# Gemini's `thought_signature`, so the agent can pass them back to the service.


class TextBlock(OpenWireModel):
    """Text from the model."""

    type: Literal["text"]
    text: str
    citations: list[Citation] | None = None


class ThinkingBlock(OpenWireModel):
    """The model's reasoning."""

    type: Literal["thinking"]
    thinking: str
    """The reasoning, or the service's encrypted reasoning when `redacted` is true."""
    signature: str | None = None
    """The service's token for passing the reasoning back to it."""
    redacted: bool | None = None


class ImageBlock(OpenWireModel):
    """An image."""

    type: Literal["image"]
    source: Source


class ToolUseBlock(OpenWireModel):
    """A call to a tool the agent runs."""

    type: Literal["tool_use"]
    id: str
    name: str
    input: dict[str, JsonValue]


class ToolResultBlock(OpenWireModel):
    """The result of a `tool_use` call, matched by `tool_use_id`."""

    type: Literal["tool_result"]
    tool_use_id: str
    content: str | list[Annotated[TextBlock | ImageBlock, Field(discriminator="type")]]
    structured_content: dict[str, JsonValue] | None = None
    """A result meant for programs, such as MCP's `structuredContent`."""
    is_error: bool | None = None


class ServerToolUseBlock(OpenWireModel):
    """A call to a tool the model service runs itself, such as web search."""

    type: Literal["server_tool_use"]
    id: str
    name: str
    input: dict[str, JsonValue]


class ServerToolResultBlock(OpenWireModel):
    """The result of a `server_tool_use` call."""

    type: Literal["server_tool_result"]
    tool_use_id: str
    name: str
    content: JsonValue
    is_error: bool | None = None


class RefusalBlock(OpenWireModel):
    """The model's text when it declined."""

    type: Literal["refusal"]
    refusal: str


ContentBlock = Annotated[
    TextBlock
    | ThinkingBlock
    | ImageBlock
    | ToolUseBlock
    | ToolResultBlock
    | ServerToolUseBlock
    | ServerToolResultBlock
    | RefusalBlock,
    Field(discriminator="type"),
]

# Event data


class Usage(WireModel):
    """Token counts and cost for one model response."""

    input_tokens: NonNegativeInt
    """All input tokens, including those read from and written to the cache."""
    output_tokens: NonNegativeInt
    """All output tokens, including reasoning tokens."""
    cache_read_input_tokens: NonNegativeInt | None = None
    """The input tokens read from the cache. Included in `input_tokens`."""
    cache_creation_input_tokens: NonNegativeInt | None = None
    """The input tokens written to the cache. Included in `input_tokens`."""
    reasoning_output_tokens: NonNegativeInt | None = None
    """The output tokens the model spent on reasoning. Included in `output_tokens`."""
    cost_usd: Annotated[float, Field(ge=0)]
    """The cost in US dollars, after any cache discount."""
    cost_source: Literal["computed", "reported", "unknown"]
    """Where `cost_usd` comes from."""


class SubagentUsage(WireModel):
    """A subagent's totals. A field is absent when the agent couldn't measure it."""

    input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    cache_read_input_tokens: NonNegativeInt | None = None
    cache_creation_input_tokens: NonNegativeInt | None = None
    reasoning_output_tokens: NonNegativeInt | None = None
    cost_usd: Annotated[float, Field(ge=0)] | None = None
    cost_source: Literal["computed", "reported", "unknown"] | None = None
    responses: NonNegativeInt | None = None
    """How many model responses the subagent made."""


class RunRequested(WireModel):
    commission: Commission | JsonValue = Field(default=None, union_mode="left_to_right")
    """The Commission as the agent received it. When it doesn't match the
    Commission spec, the JSON value received, or the text when it isn't JSON.
    Absent when the run has no Commission."""


class AgentDescribed(WireModel):
    descriptor: AgentDescriptor
    """The agent's Descriptor."""


class AgentStarted(WireModel):
    prompt: str
    """The prompt the run starts with."""
    system_prompt: str | None = None
    """The system prompt the run uses."""
    model: ModelRef
    """The model the run uses."""
    tools: list[Tool] | None = None
    """The tools the run uses."""
    mcp_servers: list[McpServer] | None = None
    """The MCP servers the run uses."""
    skills: list[Skill] | None = None
    """The skills the run uses."""
    subagents: list[Subagent] | None = None
    """The subagents the run uses."""


class AssistantMessage(WireModel):
    content: list[ContentBlock]
    """What the model produced: text, reasoning, tool calls, and other blocks."""
    model: ModelRef
    """The model the agent asked for this response."""
    response_model: str | None = None
    """The model ID the service says produced the response, when it differs from `model.id`."""
    finish_reasons: list[str] | None = None
    """Why the model stopped, exactly as the service reported it."""
    duration_ms: NonNegativeInt
    """How long the response took, ending at the event's `time`."""
    usage: Usage
    """The response's token counts and cost."""
    subagent_invocation_id: str | None = None
    """When a subagent made the response, the `invocation_id` of its `subagent_invoked`."""


class ToolInvoked(WireModel):
    tool_call_id: str
    """Identifies the call: the `id` of its `tool_use` content block."""
    tool_name: str
    """The name the agent called the tool by."""
    tool_input: dict[str, JsonValue]
    """The arguments, as in the `tool_use` block's `input`."""
    mcp_server_id: str | None = None
    """The `id` of the MCP server that runs the tool."""
    subagent_invocation_id: str | None = None
    """When a subagent made the call, the `invocation_id` of its `subagent_invoked`."""


class ToolReturned(WireModel):
    tool_call_id: str
    """As in the matching `tool_invoked`."""
    tool_name: str
    """As in the matching `tool_invoked`."""
    duration_ms: NonNegativeInt
    """How long the tool took, ending at the event's `time`."""
    tool_result: ToolResultBlock
    """The result, as the model receives it."""
    subagent_invocation_id: str | None = None
    """As in the matching `tool_invoked`."""


class SubagentInvoked(WireModel):
    subagent_name: str
    """The subagent's `name`, as in `agent_started`'s `subagents`."""
    invocation_id: str
    """Identifies this run of the subagent. When a tool call started it, the call's `tool_call_id`."""
    subagent_invocation_id: str | None = None
    """When another subagent started this one, the `invocation_id` of its `subagent_invoked`."""
    subagent_input: dict[str, JsonValue]
    """The input the subagent was given."""


class SubagentReturned(WireModel):
    subagent_name: str
    """As in the matching `subagent_invoked`."""
    invocation_id: str
    """As in the matching `subagent_invoked`."""
    subagent_invocation_id: str | None = None
    """As in the matching `subagent_invoked`."""
    duration_ms: NonNegativeInt
    """How long the subagent ran, ending at the event's `time`."""
    subagent_reason: StopReason
    """Why the subagent stopped."""
    subagent_result_text: str
    """The subagent's final text, or the error message when `subagent_reason` is `error`."""
    subagent_usage: SubagentUsage | None = None
    """The subagent's totals, when the agent can't record its responses as events of their own."""


class ErrorOccurred(WireModel):
    error_code: ErrorCode
    """What kind of error. A code this version doesn't know reads as `unknown`."""
    error_message: str
    """What went wrong, for a person to read."""
    subagent_invocation_id: str | None = None
    """When the error happened in a subagent, the `invocation_id` of its `subagent_invoked`."""

    @field_validator("error_code", mode="before")
    @classmethod
    def _unknown_code(cls, code: object) -> object:
        # Supervisors MUST treat an error code they don't know as `unknown`.
        if isinstance(code, str) and code not in ErrorCode.__args__:
            return "unknown"
        return code


class AgentStopped(WireModel):
    reason: StopReason
    """Why the run stopped."""
    output: JsonValue = None
    """The run's result as the agent reports it. Absent when the agent reports none."""


# Events


class _Event(WireModel):
    avp_version: Literal["0.1"]
    """The AVP version the event follows."""
    id: str
    """Identifies the event."""
    time: Timestamp
    """When the event happened, as an RFC 3339 timestamp."""
    run_id: str
    """The run's ID, the same on every event of the run."""
    meta: dict[str, JsonValue] | None = None
    """The agent's own annotations. AVP gives them no meaning."""


class RunRequestedEvent(_Event):
    type: Literal["run_requested"]
    data: RunRequested


class AgentDescribedEvent(_Event):
    type: Literal["agent_described"]
    data: AgentDescribed


class AgentStartedEvent(_Event):
    type: Literal["agent_started"]
    data: AgentStarted


class AssistantMessageEvent(_Event):
    type: Literal["assistant_message"]
    data: AssistantMessage


class ToolInvokedEvent(_Event):
    type: Literal["tool_invoked"]
    data: ToolInvoked


class ToolReturnedEvent(_Event):
    type: Literal["tool_returned"]
    data: ToolReturned


class SubagentInvokedEvent(_Event):
    type: Literal["subagent_invoked"]
    data: SubagentInvoked


class SubagentReturnedEvent(_Event):
    type: Literal["subagent_returned"]
    data: SubagentReturned


class ErrorOccurredEvent(_Event):
    type: Literal["error_occurred"]
    data: ErrorOccurred


class AgentStoppedEvent(_Event):
    type: Literal["agent_stopped"]
    data: AgentStopped


Event = Annotated[
    RunRequestedEvent
    | AgentDescribedEvent
    | AgentStartedEvent
    | AssistantMessageEvent
    | ToolInvokedEvent
    | ToolReturnedEvent
    | SubagentInvokedEvent
    | SubagentReturnedEvent
    | ErrorOccurredEvent
    | AgentStoppedEvent,
    Field(discriminator="type"),
]
"""One Trajectory event."""

_event = TypeAdapter[Event](Event)


def parse_trajectory_event(event: dict[str, Any] | str | bytes | bytearray) -> Event | None:
    """Validate one event, given as a dict or as JSON text. Returns None for an
    event type this version doesn't know, which a supervisor MUST skip. Raises
    ValidationError for an event of a known type that doesn't match the spec."""
    try:
        if isinstance(event, dict):
            return _event.validate_python(event)
        return _event.validate_json(event)
    except ValidationError as error:
        if any(e["type"] == "union_tag_invalid" for e in error.errors()):
            return None
        raise
