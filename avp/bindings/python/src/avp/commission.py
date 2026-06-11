"""avp.commission — Pydantic types for the AVP Commission Spec.

Defines the Commission shape (supervisor → agent setup message) and the
managed-asset entries the supervisor declares inline. This module mirrors
the [Commission spec](../../../../spec/v0.1/commission.md).

Consumers wanting only the run-config object can:

    from avp.commission import Commission, McpServerHttp, McpServerStdio

…without dragging in Trajectory / Descriptor types.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

from avp.envelope import _STRICT

_ID_PATTERN = r"^[a-z0-9_-]+$"

# `model` is a canonical models.dev slug: "<origin>/<model>" (e.g.
# "anthropic/claude-opus-4-8", "openai/gpt-4o"). The origin segment is the
# model's home namespace and the pricing key; it is independent of the
# `Provider.id` storefront that actually serves the tokens.
_MODEL_SLUG_PATTERN = r"^[^/]+/.+$"


class SecretRef(BaseModel):
    """A reference to a secret the supervisor resolves out of band.

    Carries a `vault` handle, never the secret value. The supervisor maps the
    handle to material (env var, secrets file, broker) at run time; the value
    never appears on the wire or in the trajectory. Used by `Provider.credential`
    and `McpServerHttp.auth`.
    """

    model_config = _STRICT
    vault: str = Field(min_length=1, pattern=_ID_PATTERN)


class McpServerHttp(BaseModel):
    """Inline HTTP MCP server entry in Commission.mcp_servers."""

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    type: Literal["http"]
    url: str = Field(min_length=1)
    # Non-secret request headers. Credentials go in `auth` (a SecretRef the
    # supervisor resolves out of band), not here.
    headers: dict[str, str] | None = None
    auth: SecretRef | None = None


class McpServerStdio(BaseModel):
    """Inline stdio MCP server entry in Commission.mcp_servers."""

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    type: Literal["stdio"]
    command: list[str] = Field(min_length=1)
    args: list[str] | None = None
    env: dict[str, str] | None = None


McpServer = Annotated[McpServerHttp | McpServerStdio, Field(discriminator="type")]


class Provider(BaseModel):
    """Optional LLM routing override: which storefront serves the model.

    Absent → the agent uses its native default (whatever its own environment
    configures). Present → the supervisor directs the agent at a specific
    endpoint. `id` selects the protocol/auth family (e.g. "anthropic",
    "openai", "openrouter"); `base_url` overrides the endpoint; `credential`
    references the API key by vault handle (never the value).

    The model's origin (the `Commission.model` slug's first segment) and the
    storefront `id` are independent axes: `model: "openai/gpt-4o"` with
    `provider.id: "openrouter"` reads as "OpenAI's gpt-4o, bought through
    OpenRouter". An agent that cannot speak the requested provider's protocol
    MUST fail (error_occurred + agent_stopped reason=error), never silently
    run elsewhere.
    """

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    base_url: str | None = None
    credential: SecretRef | None = None


class Skill(BaseModel):
    """Inline skill entry in Commission.skills."""

    model_config = _STRICT
    id: str = Field(min_length=1, pattern=_ID_PATTERN)
    files: dict[str, str]

    @field_validator("files")
    @classmethod
    def _require_skill_md(cls, v: dict[str, str]) -> dict[str, str]:
        if "SKILL.md" not in v:
            raise ValueError("files must contain 'SKILL.md'")
        return v

    def _frontmatter_value(self, key: str) -> str | None:
        content = self.files.get("SKILL.md", "")
        if not content.startswith("---"):
            return None
        end = content.find("---", 3)
        if end == -1:
            return None
        for line in content[3:end].splitlines():
            if line.startswith(f"{key}:"):
                return line[len(key) + 1 :].strip() or None
        return None

    @property
    def name(self) -> str | None:
        return self._frontmatter_value("name")

    @property
    def description(self) -> str | None:
        return self._frontmatter_value("description")


class SupervisorPreamble(BaseModel):
    """Identifies the supervisor that is requesting the run.

    Carried inside `Commission.supervisor` and projected onto the
    `run_requested` event's `data` (`avp.supervisor.name` +
    `avp.supervisor.version`) so a trajectory consumer can attribute the
    run to the originating supervisor without an out-of-band lookup. The
    event's `source` is `avp://agent` (the agent is the sole producer on
    the wire); supervisor attribution lives inside `data`.

    `name` SHOULD be a stable identifier for the supervisor implementation
    or instance (e.g. `"avp-cli"`, `"acme.scheduler"`).
    `version` is optional but recommended; it travels with the trajectory
    and lets auditors correlate a run with the exact supervisor build
    that requested it.
    """

    model_config = _STRICT
    name: str = Field(min_length=1)
    version: str | None = None


class Commission(BaseModel):
    """Supervisor's declaration of the supervisor-managed environment slice.

    Managed asset entries (`mcp_servers`, `skills`) carry inline connection
    material; no resolver round-trip is needed. The agent dials MCP servers
    and injects skill content directly from these fields at startup.

    Anything the agent provides on its own (in-process tools, baked-in
    skills) is invisible to AVP and the Commission entirely. The agent's own
    contribution surfaces in `agent_described.data["avp.descriptor"]` so
    consumers can audit what the agent showed up with. The agent's runtime
    layer merges its internal contribution with the Commission-managed assets
    into one bag the loop dispatches against; collisions on `id` are a
    startup error.
    """

    model_config = _STRICT

    schema_version: Literal["0.1"]
    run_id: str = Field(min_length=1)

    # Supervisor identity. Optional but RECOMMENDED. When present, the agent
    # stamps `run_requested.data.avp.supervisor.*` from this field so the
    # trajectory records who requested the run. When absent, the agent
    # still emits `run_requested` but with `avp.supervisor.name="unknown"`.
    supervisor: SupervisorPreamble | None = None

    # Supervisor-managed assets. Connection material is inline; agents dial
    # MCP servers and load skill content directly at startup.
    mcp_servers: list[McpServer] | None = None
    skills: list[Skill] | None = None

    # Optional LLM routing override. Absent → the agent's native default.
    provider: Provider | None = None

    # Allow-lists over the agent's Descriptor-declared surface, keyed by
    # `descriptor.agent_name` so one Commission can carry an explicit list
    # per agent it may run on (names live in each agent's own namespace).
    # The running agent looks up exactly its own `agent_name`:
    #
    #   - None (absent)          → every descriptor entry of that kind is
    #                              exposed (default).
    #   - map without my key     → commission_collision fail-fast: the
    #                              Commission filters this surface but was
    #                              not authored for this agent.
    #   - my key → []            → none are exposed.
    #   - my key → [n1, n2, …]   → only the listed names/ids are exposed;
    #                              the agent hides the rest from the model
    #                              and runtime-blocks any hallucinated
    #                              invocation with a `tool_returned`
    #                              (isError=True) (or, for subagents, a
    #                              `subagent_returned` with `reason=error`).
    #
    # Entries under other agents' keys are ignored by the running agent.
    # Names under the agent's own key MUST appear in the corresponding
    # descriptor field at startup or the agent emits
    # `error_occurred(code: "commission_collision")` and stops with
    # `reason=error`. Subtractive-only: these have no effect on
    # supervisor-managed assets (those are gated by being-in-the-Commission).
    # `enabled_builtin_mcp_servers` filters `descriptor.mcp_servers[].id`;
    # disabling a server prevents the agent from dialing it, so its tools
    # are unavailable for the run.
    enabled_builtin_tools: dict[str, list[str]] | None = None
    enabled_builtin_subagents: dict[str, list[str]] | None = None
    enabled_builtin_skills: dict[str, list[str]] | None = None
    enabled_builtin_mcp_servers: dict[str, list[str]] | None = None

    # Optional exact version pins, keyed by `descriptor.agent_name` and
    # matched against `descriptor.agent_version`. A pin records the agent
    # build the Commission was authored and validated against; same-name
    # tool surfaces can change behavior across builds, and a pin moves
    # that check pre-flight instead of post-hoc trajectory archaeology.
    # The running agent looks up its own `agent_name`:
    #
    #   - None (absent) / no key for me → no pin declared; run proceeds.
    #     (Deliberately the opposite default from the allowlists above:
    #     an allowlist without my key means "filtered but not authored
    #     for me"; a pin map without my key just means "nobody pinned me".)
    #   - my key present, value != my agent_version → the agent emits
    #     `error_occurred(code: "unsupported_agent_version")` and stops
    #     with `reason=error` before any model turn.
    #
    # Exact string match; no version ranges.
    agent_versions: dict[str, str] | None = None

    output_schema: dict[str, Any] | None = None

    # Agent plane (what the agent runs)
    prompt: str | None = None
    system_prompt: str | None = None
    # Canonical models.dev slug "<origin>/<model>" (e.g. "anthropic/claude-opus-4-8").
    # The pattern requires a non-empty origin and model id. Required: the origin
    # segment is the pricing key and the native-default routing hint; agents
    # split it off to get the SDK-native model id.
    model: str = Field(min_length=1, pattern=_MODEL_SLUG_PATTERN)

    # Metadata
    thread_id: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None


__all__ = [
    "Commission",
    "McpServer",
    "McpServerHttp",
    "McpServerStdio",
    "Provider",
    "SecretRef",
    "Skill",
    "SupervisorPreamble",
]
