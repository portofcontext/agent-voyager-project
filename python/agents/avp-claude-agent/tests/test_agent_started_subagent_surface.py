"""`agent_started.data.subagents` reflects the EFFECTIVE subagent
surface available to the model.

Per the Claude Agent SDK subagents docs
(https://code.claude.com/docs/en/agent-sdk/subagents):

  "Built-in general-purpose: Claude can invoke the built-in
  `general-purpose` subagent at any time via the Agent tool without
  you defining anything"

So `general-purpose` is the one SDK-runtime-bundled subagent. `Explore`
and `Plan` mentioned in the Claude Code permissions docs are
filesystem-discovered (`.claude/agents/`), not SDK-runtime defaults —
we don't surface them.

Three Commission shapes:
  - `cfg.subagents = None` → surface SDK built-ins (`general-purpose`)
  - `cfg.subagents = []` → empty surface (model has no Commission-declared
    subagents; SDK general-purpose is still available at runtime via
    Agent tool, but we don't add it back since the supervisor explicitly
    said "no subagents in Commission")
  - `cfg.subagents = [Subagent(...)]` → those custom subagents only
    (matches "tools" restriction semantics; user is being explicit)

NOTE on skills: per the Claude Agent SDK skills docs
(https://code.claude.com/docs/en/agent-sdk/skills), the SDK does NOT
bundle skills programmatically. Skills are filesystem-discovered at
runtime from `~/.claude/skills/`, project `.claude/skills/`, and plugin
paths. We can't enumerate those at translation time — so
`agent_started.data.skills` stays `cfg.skills` only. Bundled "skills"
mentioned in Claude Code docs (`/simplify`, `/debug` etc.) are CLI
features, not Python-SDK-runtime artifacts.
"""

from __future__ import annotations

from avp import Commission, Subagent
from avp.types import AgentStartedEvent
from avp_claude_agent.translator import (
    _CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS,
    ClaudeAgentTranslator,
)

from .test_translator import _FakeHookMatcher, _FakeOptions


def _new_translator(cfg: Commission):
    out: list = []
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    return t, out


def _agent_started(events) -> AgentStartedEvent:
    return next(e for e in events if isinstance(e, AgentStartedEvent))


def test_builtin_constant_includes_general_purpose() -> None:
    """Sanity check: the SDK-bundled subagent constant carries
    general-purpose. Drift detector — if the SDK ships additional
    runtime-bundled subagents the constant grows; this test stays
    loose enough to add but flags a removal as suspicious."""
    assert "general-purpose" in _CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS


def test_subagents_unset_surfaces_sdk_builtin() -> None:
    """Common case: worker doesn't declare subagents in Commission. The SDK
    runtime makes `general-purpose` available regardless. Surface it
    on agent_started so the audit trail isn't empty for default usage."""
    cfg = Commission(
        schema_version="0.1",
        run_id="builtin-subagent",
        model="claude-sonnet-4-6",
        prompt="hi",
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.subagents is not None
    names = {sa.name for sa in started.data.subagents}
    assert names == {"general-purpose"}


def test_subagents_empty_list_emits_empty_surface() -> None:
    """`cfg.subagents = []` → null on the wire (no subagents declared).
    Same convention as tools: explicit empty means "I'm telling you
    nothing's available," distinct from "use defaults."

    This shape mismatch with runtime reality (SDK still exposes
    general-purpose via the Agent tool) is acceptable: AVP Commission is
    the supervisor's view; the runtime can still expose SDK built-ins
    when Agent is in tools. Audit consumers reading subagent_invoked
    events see what actually got invoked regardless."""
    cfg = Commission(
        schema_version="0.1",
        run_id="empty-subagents",
        model="claude-sonnet-4-6",
        prompt="hi",
        subagents=[],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.subagents is None


def test_subagents_explicit_list_emits_only_those() -> None:
    """`cfg.subagents = [Subagent(...)]` → that custom subagent only.
    SDK general-purpose is NOT auto-added — the supervisor was explicit
    about its custom set."""
    cfg = Commission(
        schema_version="0.1",
        run_id="custom-subagents",
        model="claude-sonnet-4-6",
        prompt="hi",
        subagents=[
            Subagent(
                name="code-reviewer",
                description="Expert code review specialist.",
                system_prompt="You review code.",
            )
        ],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.subagents is not None
    names = {sa.name for sa in started.data.subagents}
    assert names == {"code-reviewer"}


def test_unset_subagents_does_not_collide_when_general_purpose_in_rpc() -> None:
    """Edge case: if a supervisor explicitly declares a custom subagent
    NAMED `general-purpose`, the SDK built-in dedup logic skips re-adding
    it. The custom entry wins (carries the supervisor's declared
    description/prompt)."""
    cfg = Commission(
        schema_version="0.1",
        run_id="collision",
        model="claude-sonnet-4-6",
        prompt="hi",
        subagents=[
            Subagent(
                name="general-purpose",
                description="Custom override of the SDK default.",
                system_prompt="...",
            )
        ],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.subagents is not None
    assert len(started.data.subagents) == 1
    assert started.data.subagents[0].name == "general-purpose"
    # The supervisor-declared description carries through, NOT the
    # SDK built-in (which has none anyway).
    assert started.data.subagents[0].description == "Custom override of the SDK default."


# ── Skills: pass through unchanged (SDK doesn't bundle them) ─────────────


def test_skills_unset_stays_null() -> None:
    """`cfg.skills = None` → null on the wire. The Claude Agent SDK does
    NOT programmatically bundle skills (per the SDK skills docs); they
    come from filesystem discovery at runtime, which we can't enumerate.
    So unlike tools and subagents, there's no preset to fall back to."""
    cfg = Commission(
        schema_version="0.1",
        run_id="no-skills",
        model="claude-sonnet-4-6",
        prompt="hi",
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.skills is None


def test_skills_passes_through_when_set() -> None:
    """`cfg.skills` flows through with name + `avp.source` surfaced.
    AgentStartedData schema: `skills: list[_SkillDecl] | None`.
    Description is None unless SDK enrichment fills it in."""
    from avp import Skill

    cfg = Commission(
        schema_version="0.1",
        run_id="with-skills",
        model="claude-sonnet-4-6",
        prompt="hi",
        skills=[
            Skill.model_validate({"name": "style-guide", "avp.source": "./skills/style-guide"}),
        ],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.skills is not None
    assert len(started.data.skills) == 1
    assert started.data.skills[0].name == "style-guide"
    assert started.data.skills[0].avp_source == "./skills/style-guide"
    assert started.data.skills[0].description is None
