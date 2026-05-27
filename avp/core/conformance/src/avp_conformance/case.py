"""Pydantic model for AVP conformance test cases (agent-only, v0.1).

A test case is six fields:

- `id`, `title`, `description`, `spec_refs` — identity + traceability.
- `built_in` — fixture data the SDK MUST behave as if it has built-in for
  the run. When omitted, the SDK uses its real built-ins.
- `commission` — the AVP Commission delivered to the agent.
- `expectations` — assertions over the emitted trajectory.

Tests verify that the SDK correctly merges/overrides its built-ins with the
Commission per the AVP spec. Stubbing of model responses / tool outputs /
resolver outcomes is NOT part of v0.1 conformance: cases run against the
SDK's real model, and expectations are structural (event ordering, source
field, presence of required fields), not numeric (token counts, costs).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from avp.commission import Commission
from avp.envelope import _STRICT
from avp.trajectory import StopReason

_CASE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


# ── Built-in fixture ─────────────────────────────────────────────────────────


class BuiltinTool(BaseModel):
    """One tool the case pretends the SDK has built-in."""

    model_config = _STRICT
    name: str = Field(min_length=1)
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    mcp_server_id: str | None = None


class BuiltinSkill(BaseModel):
    """One skill the case pretends the SDK has built-in."""

    model_config = _STRICT
    name: str = Field(min_length=1)
    description: str | None = None
    version: str | None = None
    source: str | None = None


class BuiltinMcpServer(BaseModel):
    """One MCP server the case pretends the SDK has built-in.

    Connection material (URL, auth, command line) is irrelevant for the
    fixture; only identity surfaces, since merge logic operates on `id`.
    """

    model_config = _STRICT
    id: str = Field(min_length=1)
    name: str | None = None
    description: str | None = None


class BuiltinSubagent(BaseModel):
    """One subagent the case pretends the SDK has built-in."""

    model_config = _STRICT
    name: str = Field(min_length=1)
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    agent_type: str | None = None


class AgentBuiltins(BaseModel):
    """Test fixture: what the case pretends the SDK has built-in for the run.

    The SDK's conformance entrypoint MUST behave as if these are its actual
    built-ins, then apply Commission overrides per the AVP merge spec. SDKs
    that can't simulate arbitrary built-ins (e.g. can't inject a fake MCP
    server into their underlying framework) will fail those cases; that's
    an SDK conformance gap, not a case-file design problem.
    """

    model_config = _STRICT

    system_prompt: str | None = None
    prompt: str | None = None
    tools: list[BuiltinTool] = Field(default_factory=list)
    skills: list[BuiltinSkill] = Field(default_factory=list)
    mcp_servers: list[BuiltinMcpServer] = Field(default_factory=list)
    subagents: list[BuiltinSubagent] = Field(default_factory=list)


# ── Expectations ─────────────────────────────────────────────────────────────


class EventMatcher(BaseModel):
    """Partial-match pattern. Every key/value in `match` must appear in the
    event with that exact value (deep-equal for nested objects). Other keys
    MAY be present in the event."""

    model_config = _STRICT
    match: dict[str, Any]
    label: str | None = None


class FinalState(BaseModel):
    """Assertions over the terminal `agent_stopped` event and run totals.

    Numeric bounds (`min_/max_total_*`) are kept for cases where the SDK
    can guarantee them (e.g. via deterministic test models), but most v0.1
    cases will only assert `stop_reason` since real-LLM runs vary.
    """

    model_config = _STRICT
    stop_reason: StopReason | None = None
    total_turns: int | None = Field(default=None, ge=0)
    min_total_cost_usd: float | None = Field(default=None, ge=0)
    max_total_cost_usd: float | None = Field(default=None, ge=0)
    min_total_tokens: int | None = Field(default=None, ge=0)
    max_total_tokens: int | None = Field(default=None, ge=0)


Ordering = Literal["in_order_subsequence", "in_order_strict", "any_order"]


class Expectations(BaseModel):
    """What the trajectory must (and must not) contain."""

    model_config = _STRICT
    events: list[EventMatcher]
    ordering: Ordering = "in_order_subsequence"
    forbidden_events: list[EventMatcher] = Field(default_factory=list)
    final_state: FinalState | None = None


# ── Top-level case ───────────────────────────────────────────────────────────


class TestCase(BaseModel):
    """One conformance test case. Agent-only for v0.1."""

    model_config = _STRICT

    id: Annotated[str, Field(pattern=_CASE_ID_PATTERN)]
    title: str
    description: str | None = None
    spec_refs: list[str] = Field(default_factory=list)
    built_in: AgentBuiltins | None = None
    commission: Commission
    expectations: Expectations
