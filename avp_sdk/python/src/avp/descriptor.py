"""Wire types for the [Agent Descriptor spec](../../../../spec/v0.1/agent-descriptor.md).

Each class matches one table in the spec's reference section.
"""

from typing import Literal

from pydantic import Field, JsonValue

from avp._base import AgentName, OpenWireModel, WireModel


class ModelPattern(WireModel):
    """Matches the `provider` and `id` of a Commission's Model. `*` matches any characters."""

    provider: str
    """A pattern for the model's `provider`, for example `"anthropic"`."""
    id: str
    """A pattern for the model's `id`, for example `"claude-*"`."""


class Tool(OpenWireModel):
    """An MCP `Tool` object, with one added field. Other MCP fields are kept."""

    name: str
    """The tool's name, as the model calls it."""
    title: str | None = None
    """A display name."""
    description: str | None = None
    """What the tool does, as the model sees it."""
    input_schema: dict[str, JsonValue] = Field(alias="inputSchema")
    """A JSON Schema for the tool's input, as the model sees it."""
    output_schema: dict[str, JsonValue] | None = Field(default=None, alias="outputSchema")
    """A JSON Schema for the tool's structured output."""
    mcp_server_id: str | None = None
    """The `id` of the MCP server the tool comes from. Absent for any tool that
    does not come from an MCP server."""


class McpServer(WireModel):
    """An MCP server the agent comes with. Connection details stay inside the agent."""

    id: str
    """Identifies the server. A Tool's `mcp_server_id` refers to it."""
    name: str | None = None
    """A display name, when it differs from `id`."""
    description: str | None = None
    """What the server provides."""
    status: Literal["connected", "failed", "needs-auth", "disabled"] | None = None
    """The result of the agent's attempt to connect."""


class Skill(OpenWireModel):
    """The frontmatter of a skill's `SKILL.md`, as defined by Agent Skills, with
    one added field. Other frontmatter fields are kept."""

    name: str
    """The skill's name."""
    description: str
    """What the skill does and when to use it."""
    source: str | None = None
    """A `file:` URI for the directory that contains the skill's `SKILL.md`, as
    the path appears inside the agent's environment."""


class Subagent(WireModel):
    """A subagent that ships with the agent. It does not inherit the agent's items."""

    name: str
    """Identifies the subagent."""
    description: str | None = None
    """What the subagent does."""
    system_prompt: str | None = None
    """The subagent's system prompt."""
    tools: list[Tool] | None = None
    """The subagent's tools."""
    mcp_servers: list[McpServer] | None = None
    """The subagent's MCP servers."""
    skills: list[Skill] | None = None
    """The subagent's skills."""


class AgentDescriptor(WireModel):
    """What an agent comes with before any Commission."""

    avp_version: Literal["0.1"]
    """The AVP version the Descriptor follows."""
    agent_name: AgentName
    """The agent's name."""
    agent_version: str
    """The agent's version."""
    supported_models: list[ModelPattern] | None = None
    """The models the agent can run. Absent means the agent does not say."""
    system_prompt: str | None = None
    """The system prompt the agent comes with."""
    tools: list[Tool] | None = None
    """The agent's built-in tools, including those that come from its MCP servers."""
    mcp_servers: list[McpServer] | None = None
    """The MCP servers the agent comes with."""
    skills: list[Skill] | None = None
    """The skills the agent comes with."""
    subagents: list[Subagent] | None = None
    """The subagents the agent comes with."""
