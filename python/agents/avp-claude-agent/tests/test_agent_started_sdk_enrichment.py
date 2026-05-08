"""`agent_started` enrichment via `ClaudeSDKClient.get_context_usage()`.

After `client.connect()` returns, the SDK has loaded its full tool
catalog, agents (subagents), and skills (with frontmatter parsed). The
translator pulls that view via `get_context_usage()` and merges it into
`agent_started.data.{tools,skills,subagents}` so the input event carries
real descriptions / agentType / source rather than name-only stubs.

Pre-fix the translator emitted `agent_started` synchronously with
commission-only data, leaving descriptions null even when the SDK had them.
Auditors had to derive that surface from post-hoc events. Now the input
event carries it upfront.

Fallback: when `get_context_usage` is missing (older SDK, test fakes)
or raises, the translator falls back to commission-only emission — same v0.1
behavior, lifecycle marker still on the wire.
"""

from __future__ import annotations

import asyncio
from typing import Any

from avp import Commission, Skill, Subagent
from avp.types import AgentStartedEvent
from avp_claude_agent.translator import ClaudeAgentTranslator

from .test_translator import _FakeHookMatcher, _FakeOptions


def _new_translator(commission: Commission) -> tuple[ClaudeAgentTranslator, list]:
    out: list = []
    t = ClaudeAgentTranslator(
        commission,
        on_event=out.append,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    return t, out


def _agent_started(events) -> AgentStartedEvent:
    return next(e for e in events if isinstance(e, AgentStartedEvent))


class _UsageClient:
    """Stand-in for `ClaudeSDKClient.get_context_usage()`. The real
    method returns a `ContextUsageResponse` TypedDict; we mirror the
    dict shape with the fields the translator consumes."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    async def get_context_usage(self) -> dict[str, Any]:
        return self._response


# ── Tools: SDK-side descriptions surface on the wire ─────────────────


def test_systemtools_descriptions_attach_to_builtin_tool_decls() -> None:
    """SDK reports `Read` with a description; the translator merges it
    onto the built-in tool decl rather than leaving it null."""
    commission = Commission(
        schema_version="0.1",
        run_id="enriched-tools",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    t, out = _new_translator(commission)
    client = _UsageClient(
        {
            "systemTools": [
                {"name": "Read", "description": "Read a file from disk."},
                {"name": "Bash", "description": "Run a shell command."},
            ],
            "agents": [],
            "skills": [],
        }
    )
    asyncio.run(t._emit_agent_started_with_sdk_enrichment(client))

    started = _agent_started(out)
    assert started.data.tools is not None
    by_name = {tool.name: tool for tool in started.data.tools}
    assert by_name["Read"].description == "Read a file from disk."
    assert by_name["Bash"].description == "Run a shell command."


# ── Subagents: agentType + description ───────────────────────────────


def test_agents_attach_description_and_agent_type_for_builtin() -> None:
    """SDK reports `general-purpose` with a description + agentType.
    The built-in subagent decl picks both up so the supervisor's
    audit trail shows what the agent actually was."""
    commission = Commission(
        schema_version="0.1",
        run_id="enriched-subagent",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    t, out = _new_translator(commission)
    client = _UsageClient(
        {
            "agents": [
                {
                    "agentType": "general-purpose",
                    "description": "Default catch-all subagent.",
                }
            ],
        }
    )
    asyncio.run(t._emit_agent_started_with_sdk_enrichment(client))

    started = _agent_started(out)
    assert started.data.subagents is not None
    by_name = {sa.name: sa for sa in started.data.subagents}
    sa = by_name["general-purpose"]
    assert sa.description == "Default catch-all subagent."
    assert sa.avp_agent_type == "general-purpose"


def test_cfg_declared_subagent_description_is_not_overwritten() -> None:
    """Like with tools: when the supervisor declares a Subagent, that
    description is canonical. Enrichment only fills in the BUILT-IN
    decls, not commission-declared ones."""
    commission = Commission(
        schema_version="0.1",
        run_id="rpc-subagent-supersedes-sdk",
        model="claude-sonnet-4-6",
        prompt="hi",
        subagents=[
            Subagent(
                name="code-reviewer",
                description="Supervisor-authored review specialist.",
                system_prompt="...",
                exposed=["*"],
            )
        ],
        exposed=["*"],
    )
    t, out = _new_translator(commission)
    client = _UsageClient(
        {
            "agents": [
                {
                    "agentType": "code-reviewer",
                    "description": "SDK-loaded reviewer (should NOT win).",
                }
            ],
        }
    )
    asyncio.run(t._emit_agent_started_with_sdk_enrichment(client))

    started = _agent_started(out)
    assert started.data.subagents is not None
    assert len(started.data.subagents) == 1
    assert started.data.subagents[0].description == "Supervisor-authored review specialist."


# ── Skills: SDK-loaded filesystem skills appear; commission gets descriptions ──


def test_sdk_loaded_filesystem_skills_appear_on_wire() -> None:
    """The SDK loads skills from `~/.claude/skills/` and project paths
    that aren't in `commission.skills`. Surface them so the audit trail
    reflects what the agent ACTUALLY had access to, not just what the
    supervisor declared."""
    commission = Commission(
        schema_version="0.1",
        run_id="filesystem-skills",
        model="claude-sonnet-4-6",
        prompt="hi",
        # Note: no commission.skills — these all come from filesystem.,
        exposed=["*"],
    )
    t, out = _new_translator(commission)
    client = _UsageClient(
        {
            "skills": [
                {
                    "name": "deploy",
                    "description": "Run the deploy script.",
                    "source": "/Users/x/projects/foo/.claude/skills/deploy",
                },
                {
                    "name": "lint",
                    "description": "Run the linter.",
                    "source": "/Users/x/.claude/skills/lint",
                },
            ],
        }
    )
    asyncio.run(t._emit_agent_started_with_sdk_enrichment(client))

    started = _agent_started(out)
    assert started.data.skills is not None
    by_name = {s.name: s for s in started.data.skills}
    assert set(by_name) == {"deploy", "lint"}
    assert by_name["deploy"].description == "Run the deploy script."
    assert by_name["deploy"].avp_source == "/Users/x/projects/foo/.claude/skills/deploy"
    assert by_name["lint"].description == "Run the linter."


def test_cfg_skill_gets_sdk_description_when_sdk_loaded_it() -> None:
    """`commission.skills` declares a name + source; the SDK loaded the
    skill from that source and parsed its frontmatter description.
    Merge: commission supplies the source, SDK supplies the description."""
    commission = Commission(
        schema_version="0.1",
        run_id="skill-merge",
        model="claude-sonnet-4-6",
        prompt="hi",
        skills=[
            Skill.model_validate({"name": "style-guide", "avp.source": "./skills/style-guide"}),
        ],
        exposed=["*"],
    )
    t, out = _new_translator(commission)
    client = _UsageClient(
        {
            "skills": [
                {
                    "name": "style-guide",
                    "description": "House code style rules.",
                    "source": "./skills/style-guide",
                }
            ],
        }
    )
    asyncio.run(t._emit_agent_started_with_sdk_enrichment(client))

    started = _agent_started(out)
    assert started.data.skills is not None
    assert len(started.data.skills) == 1
    s = started.data.skills[0]
    assert s.name == "style-guide"
    assert s.description == "House code style rules."
    assert s.avp_source == "./skills/style-guide"


# ── Fallback paths ───────────────────────────────────────────────────


def test_fallback_when_client_has_no_get_context_usage() -> None:
    """SDKs predating get_context_usage → commission-only emission. Same
    behavior as v0.1; lifecycle invariant preserved."""

    class _ClientWithoutUsage:
        pass

    commission = Commission(
        schema_version="0.1",
        run_id="no-usage",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    t, out = _new_translator(commission)
    asyncio.run(t._emit_agent_started_with_sdk_enrichment(_ClientWithoutUsage()))

    started = _agent_started(out)
    assert started.data.subagents is not None
    # general-purpose still surfaced from the commission-side preset; just no
    # description / agentType because we couldn't fetch them.
    by_name = {sa.name: sa for sa in started.data.subagents}
    assert "general-purpose" in by_name
    assert by_name["general-purpose"].description is None
    assert by_name["general-purpose"].avp_agent_type is None


def test_fallback_when_get_context_usage_raises() -> None:
    """If the call raises (transport hiccup, version mismatch), the
    translator falls back to commission-only emission rather than crashing
    the run."""

    class _Boom:
        async def get_context_usage(self):
            raise RuntimeError("sdk transport went away")

    commission = Commission(
        schema_version="0.1",
        run_id="boom",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    t, out = _new_translator(commission)
    asyncio.run(t._emit_agent_started_with_sdk_enrichment(_Boom()))

    started = _agent_started(out)
    # Lifecycle marker on wire; fields fall back to commission-only defaults.
    assert started.data.subagents is not None


def test_fallback_when_response_shape_is_wrong() -> None:
    """If the SDK returns something unexpected (string, list, dict
    without the keys we read), defensive parsing falls back to empty
    enrichment rather than blowing up."""

    class _Garbage:
        async def get_context_usage(self):
            return "not a dict at all"

    commission = Commission(
        schema_version="0.1",
        run_id="garbage",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    t, out = _new_translator(commission)
    asyncio.run(t._emit_agent_started_with_sdk_enrichment(_Garbage()))

    started = _agent_started(out)
    assert started.data.subagents is not None  # still emitted


# ── Idempotency: post-connect emit does not double-emit ──────────────


def test_double_emit_is_idempotent() -> None:
    """If something causes `_emit_agent_started` to be invoked twice
    (e.g., a fallback path runs after the enriched path), only one
    `agent_started` event lands on the wire. Required for lifecycle
    correctness."""
    commission = Commission(
        schema_version="0.1",
        run_id="idempotent",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    t, out = _new_translator(commission)
    client = _UsageClient({"systemTools": [{"name": "Read", "description": "rd"}]})
    asyncio.run(t._emit_agent_started_with_sdk_enrichment(client))
    t._emit_agent_started()  # second call — should be a no-op
    started_events = [e for e in out if isinstance(e, AgentStartedEvent)]
    assert len(started_events) == 1
    # And the enriched description survives.
    by_name = {tool.name: tool for tool in started_events[0].data.tools or []}
    assert by_name["Read"].description == "rd"
