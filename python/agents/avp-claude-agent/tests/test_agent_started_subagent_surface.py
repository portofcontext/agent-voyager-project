"""`agent_started.data.subagents` reflects the effective subagent surface
the model sees.

Per the Claude Agent SDK subagents docs, `general-purpose` is the one
SDK-runtime-bundled subagent (`Explore` / `Plan` are filesystem-discovered).

Commission semantics (v0.1 refs-only):
  - `cfg.subagents = None`              → surface SDK built-ins (`general-purpose`)
  - `cfg.subagents = []`                → empty surface (supervisor explicitly
                                           declared no managed subagents)
  - `cfg.subagents = [SubagentRef(...)]` → id-only stub appears on the wire;
                                            descriptions arrive separately on
                                            `managed_ref_resolved` after the
                                            resolver runs (spec/resolver/v0.1-beta/resolver.md).
"""

from __future__ import annotations

from avp import Commission, SubagentRef
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
    """Sanity check: the SDK-bundled subagent constant carries general-purpose."""
    assert "general-purpose" in _CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS


def test_subagents_unset_surfaces_sdk_builtin() -> None:
    """`cfg.subagents = None` → SDK built-in `general-purpose` shows up on
    the wire so the audit trail isn't empty for default usage."""
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


def test_subagents_explicit_refs_emit_id_only_stubs() -> None:
    """Commission-managed subagent refs surface on `agent_started.data.subagents[]`
    as id-only stubs. Resolved metadata (description, inputSchema) arrives
    on `managed_ref_resolved` after the resolver runs at startup."""
    cfg = Commission(
        schema_version="0.1",
        run_id="managed-subagents",
        model="claude-sonnet-4-6",
        prompt="hi",
        subagents=[SubagentRef(id="code-reviewer", ref="sk_code_reviewer_v1")],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.subagents is not None
    names = {sa.name for sa in started.data.subagents}
    # `code-reviewer` is the managed ref's id; `general-purpose` is the
    # SDK built-in (always surfaced when not shadowed by a managed entry).
    assert names == {"code-reviewer", "general-purpose"}
    code_reviewer = next(sa for sa in started.data.subagents if sa.name == "code-reviewer")
    # Description is honest-null at agent_started time — it arrives via
    # the resolved metadata recorded on managed_ref_resolved.
    assert code_reviewer.description is None


def test_managed_subagent_shadows_sdk_builtin_when_id_collides() -> None:
    """If a supervisor declares a managed subagent with id `general-purpose`,
    the wire shows just the managed entry (the SDK built-in dedup skips
    re-adding it)."""
    cfg = Commission(
        schema_version="0.1",
        run_id="collision",
        model="claude-sonnet-4-6",
        prompt="hi",
        subagents=[SubagentRef(id="general-purpose", ref="sk_custom")],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.subagents is not None
    assert len(started.data.subagents) == 1
    assert started.data.subagents[0].name == "general-purpose"


# ── Skills: id-only stubs at agent_started; content arrives via resolver ────


def test_skills_unset_stays_null() -> None:
    """`cfg.skills = None` → null on the wire."""
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


def test_skills_pass_through_name_when_resolution_carries_no_description() -> None:
    """If the resolver returned material with no `description`,
    `agent_started.data.skills[].description` stays None — the wire field
    is optional and we don't fabricate."""
    from avp import SkillRef

    cfg = Commission(
        schema_version="0.1",
        run_id="with-skills",
        model="claude-sonnet-4-6",
        prompt="hi",
        skills=[SkillRef(id="style-guide", ref="sha256:abc")],
    )
    t, out = _new_translator(cfg)
    # Simulate resolution that returned only content (description-less).
    t._resolved_skills["style-guide"] = {"content": "..."}
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.skills is not None
    assert len(started.data.skills) == 1
    assert started.data.skills[0].name == "style-guide"
    assert started.data.skills[0].description is None


def test_skills_surface_description_from_resolved_material() -> None:
    """When the resolver returns SKILL.md frontmatter alongside content,
    the description flows onto `agent_started.data.skills[].description`
    so consumers don't have to cross-reference an external resolver."""
    from avp import SkillRef

    cfg = Commission(
        schema_version="0.1",
        run_id="with-skills",
        model="claude-sonnet-4-6",
        prompt="hi",
        skills=[SkillRef(id="style-guide", ref="sha256:abc")],
    )
    t, out = _new_translator(cfg)
    t._resolved_skills["style-guide"] = {
        "description": "House code style for Python.",
        "source": "skills/style-guide.md",
        "content": "...",
    }
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.skills is not None
    assert len(started.data.skills) == 1
    skill = started.data.skills[0]
    assert skill.name == "style-guide"
    assert skill.description == "House code style for Python."
    assert skill.avp_source == "skills/style-guide.md"
