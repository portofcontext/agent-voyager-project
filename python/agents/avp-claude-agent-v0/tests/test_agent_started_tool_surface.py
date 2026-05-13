"""`agent_started.data.tools` reflects the effective tool surface the
model sees, and `Commission.enabled_builtin_tools` (spec/v0.1/commission.md §4 allowlist)
maps to the Claude Agent SDK's `tools` parameter.

Three Commission shapes, three behaviors:
  - `enabled_builtin_tools=[n1, n2]` → SDK gets `tools=[n1, n2]`; only
    those names surface on `agent_started.data.tools[]`.
  - `enabled_builtin_tools=[]`        → SDK gets `tools=[]`; surface is
    empty (model sees no built-ins).
  - `enabled_builtin_tools=None` (absent) → SDK uses its claude_code
    preset; the translator enumerates the documented preset names on
    `agent_started.data.tools[]` so the common "let-the-SDK-handle-it"
    case isn't blank on the wire.

Names + dispatch_target only — no descriptions for SDK built-ins. The
SDK doesn't expose its catalog programmatically; the source of truth
for descriptions is Claude Code documentation, not us.
"""

from __future__ import annotations

from avp.commission import Commission
from avp.trajectory import AgentStartedEvent
from avp_claude_agent.translator import (
    _CLAUDE_CODE_PRESET_TOOLS,
    ClaudeAgentTranslator,
    _make_builtin_tool_decl,
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


# ── Plumbing: enabled_builtin_tools → SDK `tools` (NOT `allowed_tools`) ──────


def test_enabled_builtin_tools_maps_to_sdk_tools_not_allowed_tools() -> None:
    """SDK `allowed_tools` is the auto-approve list — does NOT restrict
    visibility. The exposure filter must land on SDK `tools`."""
    cfg = Commission(
        schema_version="0.1",
        run_id="plumbing",
        model="claude-sonnet-4-6",
        prompt="hi",
        enabled_builtin_tools=["Read", "Bash"],
    )
    t, _ = _new_translator(cfg)
    options = t._build_sdk_options()
    assert options.kwargs["tools"] == ["Read", "Bash"]
    assert "allowed_tools" not in options.kwargs


def test_empty_enabled_builtin_tools_passes_empty_list_to_sdk() -> None:
    """`enabled_builtin_tools=[]` means "no built-ins this run." Pydantic
    keeps the empty list (doesn't coerce to None) so the empty disabled
    surface flows through to the SDK kwargs verbatim."""
    cfg = Commission(
        schema_version="0.1",
        run_id="empty",
        model="claude-sonnet-4-6",
        prompt="hi",
        enabled_builtin_tools=[],
    )
    t, _ = _new_translator(cfg)
    options = t._build_sdk_options()
    assert options.kwargs["tools"] == []


def test_unset_enabled_builtin_tools_omits_sdk_tools_kwarg() -> None:
    """`enabled_builtin_tools=None` means "use SDK defaults" — pass
    nothing so the SDK falls back to its claude_code preset."""
    cfg = Commission(
        schema_version="0.1",
        run_id="unset",
        model="claude-sonnet-4-6",
        prompt="hi",
    )
    t, _ = _new_translator(cfg)
    options = t._build_sdk_options()
    assert "tools" not in options.kwargs


# ── Helper unit tests ────────────────────────────────────────────────────


def test_make_builtin_tool_decl_known_tool_includes_bundled_schema() -> None:
    decl = _make_builtin_tool_decl("Read")
    # Core identity + dispatch tagging.
    assert decl["name"] == "Read"
    assert decl["avp.dispatch_target"] == "local"
    # Bundled schema material is surfaced so consumers don't have to
    # cross-reference external docs.
    assert "description" in decl
    assert isinstance(decl["inputSchema"], dict)
    assert decl["inputSchema"]["type"] == "object"
    assert "file_path" in decl["inputSchema"]["properties"]
    # Provenance tags let consumers detect staleness.
    assert decl["avp.tool.schema_source"] == "avp-claude-agent-bundled"
    assert decl["avp.tool.schema_snapshot_date"]


def test_make_builtin_tool_decl_unknown_name_falls_back_to_name_only() -> None:
    decl = _make_builtin_tool_decl("FutureSDKTool")
    assert decl == {"name": "FutureSDKTool", "avp.dispatch_target": "local"}


def test_make_builtin_tool_decl_mcp_prefixed_name_tags_server_id() -> None:
    decl = _make_builtin_tool_decl("mcp__weather__forecast")
    assert decl["name"] == "mcp__weather__forecast"
    assert decl["avp.dispatch_target"] == "mcp_server"
    assert decl["avp.mcp_server_id"] == "weather"


def test_make_builtin_tool_decl_mcp_with_underscores_in_server_name() -> None:
    decl = _make_builtin_tool_decl("mcp__my_company_tools__lookup_user")
    assert decl["avp.mcp_server_id"] == "my_company_tools"


def test_preset_constant_includes_documented_claude_code_tools() -> None:
    """Drift detector — Claude Code adding new built-ins is fine, but
    removing one of the canonical names is suspicious."""
    expected = {"Read", "Write", "Edit", "Glob", "Grep", "Bash"}
    assert expected.issubset(set(_CLAUDE_CODE_PRESET_TOOLS))


# ── Surface reporting on agent_started.data.tools ──────────────────────────


def test_enabled_builtin_tools_explicit_list_emits_only_those_names() -> None:
    cfg = Commission(
        schema_version="0.1",
        run_id="restricted",
        model="claude-sonnet-4-6",
        prompt="hi",
        enabled_builtin_tools=["Read", "Write", "Bash"],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    tools = started.data.tools
    assert tools is not None
    assert {tool.name for tool in tools} == {"Read", "Write", "Bash"}
    for tool in tools:
        assert tool.avp_dispatch_target == "local"


def test_empty_enabled_builtin_tools_emits_empty_surface() -> None:
    """`enabled_builtin_tools=[]` → no built-ins on the wire. Distinguishes
    from absent (preset) on the wire: model sees nothing."""
    cfg = Commission(
        schema_version="0.1",
        run_id="empty-surface",
        model="claude-sonnet-4-6",
        prompt="hi",
        enabled_builtin_tools=[],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    assert started.data.tools is None


def test_unset_enabled_builtin_tools_emits_full_preset() -> None:
    """`Commission.enabled_builtin_tools` absent → SDK falls back to the
    claude_code preset. The translator enumerates that preset on
    agent_started so the default-usage case has an audit trail."""
    cfg = Commission(
        schema_version="0.1",
        run_id="preset",
        model="claude-sonnet-4-6",
        prompt="hi",
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    tools = started.data.tools
    assert tools is not None
    surfaced = {tool.name for tool in tools}
    assert surfaced == set(_CLAUDE_CODE_PRESET_TOOLS)
    for tool in tools:
        assert tool.avp_dispatch_target == "local"
        # Every preset tool carries a bundled description + inputSchema
        # plus provenance tags. The catalog asserts preset/catalog parity
        # at import, so the lookup is guaranteed to hit for preset names.
        assert tool.description
        assert tool.inputSchema is not None
        assert tool.inputSchema["type"] == "object"
