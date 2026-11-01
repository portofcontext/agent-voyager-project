"""Wire types for the Commission spec (`spec/v0.1/commission.md`).

Each class matches one table in the spec's reference section.
"""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, StringConstraints, field_validator

from avp._base import AgentName, ObjectSchema, WireModel


class Supervisor(WireModel):
    """The supervisor that wrote the Commission."""

    name: str
    """The supervisor's name, for example `"avp-cli"`."""
    version: str | None = None
    """The supervisor's version."""


class ProxySecret(WireModel):
    """A secret that a proxy outside the agent holds and adds to its requests."""

    proxy: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$")]
    """The name of a credential that a proxy outside the agent holds. The proxy
    adds it to the agent's matching requests, so the agent never receives its
    value."""


class EnvSecret(WireModel):
    """A secret in a variable of the agent's environment."""

    env: Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
    """The name of a variable in the agent's environment that holds the secret,
    for example `"TEST_DB_PASSWORD"`."""


SecretRef = ProxySecret | EnvSecret
"""A Secret reference: names a secret without containing it."""


class ModelRef(WireModel):
    """A Model without its `credential`, as the Trajectory reports it."""

    provider: Annotated[str, StringConstraints(pattern=r"^[a-z0-9._-]+$")]
    """The service that runs the model, for example `"anthropic"`,
    `"amazon-bedrock"`, or `"openrouter"`. It decides which API the agent calls
    and how it authenticates."""
    id: str
    """The model's ID at that service, as the agent sends it, for example
    `"claude-sonnet-4-6"`."""
    base_url: str | None = None
    """The URL of the service's API. Absent means the service's default."""


class Model(ModelRef):
    """A model as one service offers it, named with models.dev provider and model IDs."""

    credential: SecretRef | None = None
    """The API key for the service. Absent means the agent uses whatever
    credential its environment has for the service. With `proxy`, the proxy
    holds the key alone and adds it to requests the way `provider`'s API
    expects, for example as Anthropic's `x-api-key` header or as
    `Authorization: Bearer <key>`."""


class _McpServerBase(WireModel):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$")]
    """Identifies the server."""
    name: str | None = None
    """A display name, when it differs from `id`."""
    description: str | None = None
    """What the server provides."""


class McpServerHttp(_McpServerBase):
    """An MCP server the agent connects to over Streamable HTTP."""

    type: Literal["http"]
    url: str
    """The server's URL."""
    headers: dict[str, str | SecretRef] | None = None
    """HTTP headers to send with each request. A Secret reference's secret is
    the header's entire value."""


class McpServerStdio(_McpServerBase):
    """An MCP server the agent starts as a local program and talks to over stdio."""

    type: Literal["stdio"]
    command: list[str] = Field(min_length=1)
    """The program and its arguments, for example `["npx", "-y", "@example/db-mcp"]`."""
    env: dict[str, str | EnvSecret] | None = None
    """Environment variables to set for the program, on top of those the
    agent's MCP client gives it."""


McpServer = Annotated[McpServerHttp | McpServerStdio, Field(discriminator="type")]
"""An MCP server entry: how the agent connects to one MCP server."""


class Skill(WireModel):
    """A skill directory, as defined by Agent Skills, carried in the Commission."""

    name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)]
    """The skill's name. Equals the `name` in the frontmatter of its `SKILL.md`."""
    files: dict[str, str] = Field(json_schema_extra={"required": ["SKILL.md"]})
    """The skill's files: each key is a path relative to the skill directory,
    and each value is the file's UTF-8 content. Includes `"SKILL.md"`."""

    @field_validator("files")
    @classmethod
    def _has_skill_md(cls, files: dict[str, str]) -> dict[str, str]:
        if "SKILL.md" not in files:
            raise ValueError('files must include "SKILL.md"')
        return files


class AgentSettings(WireModel):
    """Settings for the agent whose `agent_name` is their key in `agents`."""

    version: str | None = None
    """The `agent_version` the Commission was written for."""
    enabled_tools: list[str] | None = None
    """The built-in tools the run may use, by name. Covers only tools without an
    `mcp_server_id`."""
    enabled_subagents: list[str] | None = None
    """The built-in subagents the run may use, by name."""
    enabled_skills: list[str] | None = None
    """The built-in skills the run may use, by name."""
    enabled_mcp_servers: list[str] | None = None
    """The built-in MCP servers the run may use, by `id`."""


class Commission(WireModel):
    """What one run should do: the task and the settings for the run."""

    avp_version: Literal["0.1"]
    """The AVP version the Commission follows."""
    run_id: str
    """The run's ID, chosen by the supervisor."""
    model: Model
    """The model to run, and the service that runs it."""
    system_prompt: str | None = None
    """The system prompt for the run. It replaces the agent's own."""
    prompt: str
    """The first user message of the run."""
    supervisor: Supervisor | None = None
    """The supervisor that wrote the Commission."""
    mcp_servers: list[McpServer] | None = None
    """MCP servers to add for the run."""
    skills: list[Skill] | None = None
    """Skills to add for the run."""
    agents: dict[AgentName, AgentSettings] | None = None
    """Settings for specific agents, keyed by `agent_name`."""
    output_schema: ObjectSchema | None = None
    """A JSON Schema for the agent's final output. Its `type` is `"object"`."""
    thread_id: str | None = None
    """An ID that groups related runs, such as the turns of one conversation."""
    tags: list[str] | None = None
    """Labels for the run."""
    meta: dict[str, JsonValue] | None = None
    """Key-value data for the supervisor's own use."""
