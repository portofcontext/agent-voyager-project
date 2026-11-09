"""Runtime reporting inputs to Recorder, not a trajectory wire contract."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue

from avp._base import OpenWireModel, WireModel
from avp.commission import ModelRef
from avp.descriptor import McpServer, Skill, Subagent, Tool

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

CostSource = Literal["computed", "reported", "unknown"]
"""Where a response's `cost_usd` comes from."""

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

# Usage reports


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
    cost_source: CostSource
    """Where `cost_usd` comes from."""


class SubagentUsage(WireModel):
    """A subagent's totals. A field is absent when the agent couldn't measure it."""

    input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    cache_read_input_tokens: NonNegativeInt | None = None
    cache_creation_input_tokens: NonNegativeInt | None = None
    reasoning_output_tokens: NonNegativeInt | None = None
    cost_usd: Annotated[float, Field(ge=0)] | None = None
    cost_source: CostSource | None = None
    responses: NonNegativeInt | None = None
    """How many model responses the subagent made."""


class RunContext(WireModel):
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
