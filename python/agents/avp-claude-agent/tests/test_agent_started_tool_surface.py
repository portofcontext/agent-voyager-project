"""`agent_started.data.tools` reflects the EFFECTIVE tool surface the
model sees. Two distinct concerns the translator gets right:

1. **Plumbing**: AVP `Commission.allowed_tools` (SPEC.md §8.1: exposure
   filter) maps to SDK `ClaudeAgentOptions.tools`, NOT to SDK
   `allowed_tools` (which is the auto-approval list, doesn't restrict
   visibility). Earlier the translator mapped wrong; the AVP "MUST
   expose ONLY" contract was being violated silently.

2. **Surface reporting**: three Commission shapes, three behaviors so the
   wire accurately reflects what the model sees:
     - `allowed_tools=["Read",...]`  → restricted to those names
     - `allowed_tools=[]`            → no tools at all
     - `allowed_tools=None` (unset) → SDK's claude_code preset; we
       enumerate the documented preset names so the common
       "let-the-SDK-handle-it" case isn't blank on the wire.

Names + dispatch_target only — no descriptions for SDK built-ins. The
SDK doesn't expose its catalog programmatically; the source of truth
for descriptions is Claude Code documentation, not us.
"""

from __future__ import annotations

from avp import Commission
from avp.types import AgentStartedEvent
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


# ── Plumbing fix: allowed_tools maps to SDK `tools` not SDK `allowed_tools` ──


def test_config_allowed_tools_maps_to_sdk_tools_not_allowed_tools() -> None:
    """The plumbing bug: AVP allowed_tools means "exposure filter" per
    SPEC.md §8.1. SDK `allowed_tools` is the auto-approve list and does
    NOT restrict visibility. We must map AVP allowed_tools → SDK tools."""
    cfg = Commission(
        schema_version="0.1",
        run_id="plumbing",
        model="claude-sonnet-4-6",
        prompt="hi",
        allowed_tools=["Read", "Bash"],
    )
    t, _ = _new_translator(cfg)
    options = t._build_sdk_options()
    # The exposure filter MUST land on SDK `tools`.
    assert options.kwargs["tools"] == ["Read", "Bash"]
    # SDK `allowed_tools` (auto-approve) MUST NOT carry it — that was the
    # earlier mismapping that broke AVP semantics.
    assert "allowed_tools" not in options.kwargs


def test_empty_allowed_tools_passes_empty_list_to_sdk() -> None:
    """`Commission.allowed_tools=[]` means "no tools" per AVP. SDK accepts
    `tools=[]` to disable all built-ins. Verify the empty list flows
    through (Pydantic doesn't drop it as falsy)."""
    cfg = Commission(
        schema_version="0.1",
        run_id="empty",
        model="claude-sonnet-4-6",
        prompt="hi",
        allowed_tools=[],
    )
    t, _ = _new_translator(cfg)
    options = t._build_sdk_options()
    assert options.kwargs["tools"] == []


def test_unset_allowed_tools_omits_sdk_tools_kwarg() -> None:
    """`Commission.allowed_tools=None` means "use SDK defaults" — pass nothing
    to the SDK so it falls back to its claude_code preset."""
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


def test_make_builtin_tool_decl_emits_name_and_local_dispatch() -> None:
    """Builtin SDK tool: name + dispatch_target=local. No description —
    we don't author what we can't authoritatively source."""
    decl = _make_builtin_tool_decl("Read")
    assert decl == {"name": "Read", "avp.dispatch_target": "local"}


def test_make_builtin_tool_decl_unknown_name_same_shape() -> None:
    """Unknown / future tool names get the same shape — no special
    casing for "well-known" names."""
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
    """Sanity check: the preset constant carries the canonical tool
    names. Drift detector — if Claude Code ships new built-ins the
    test stays loose enough to add them but a removal is suspicious."""
    expected = {"Read", "Write", "Edit", "Glob", "Grep", "Bash"}
    assert expected.issubset(set(_CLAUDE_CODE_PRESET_TOOLS))


# ── Surface reporting: three Commission shapes, three behaviors ──────────────


def test_allowed_tools_explicit_list_emits_only_those_names() -> None:
    """`Commission.allowed_tools=["Read","Write","Bash"]` → exactly those
    three appear on agent_started. Model can ONLY see these."""
    cfg = Commission(
        schema_version="0.1",
        run_id="restricted",
        model="claude-sonnet-4-6",
        prompt="hi",
        allowed_tools=["Read", "Write", "Bash"],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    tools = started.data.tools
    assert tools is not None
    assert {tool.name for tool in tools} == {"Read", "Write", "Bash"}
    for tool in tools:
        assert tool.avp_dispatch_target == "local"


def test_allowed_tools_empty_emits_empty_surface() -> None:
    """`Commission.allowed_tools=[]` → no tools. Distinguishes from
    "preset" on the wire: model can see nothing."""
    cfg = Commission(
        schema_version="0.1",
        run_id="empty-surface",
        model="claude-sonnet-4-6",
        prompt="hi",
        allowed_tools=[],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    started = _agent_started(out)
    # No RPC tools, no allowed builtins → tools is None (empty list
    # collapses to None on the wire to match _ToolDecl.list[_ToolDecl] | None).
    assert started.data.tools is None


def test_allowed_tools_unset_emits_full_preset() -> None:
    """`Commission.allowed_tools=None` → SDK uses the `claude_code` preset.
    The translator surfaces the preset's documented tool names so the
    common "let-the-SDK-handle-it" case has a usable audit trail."""
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
    # The full preset shows up — wire is no longer null for default usage.
    assert surfaced == set(_CLAUDE_CODE_PRESET_TOOLS)
    for tool in tools:
        assert tool.avp_dispatch_target == "local"
        assert tool.description is None  # we don't author descriptions


def test_mcp_prefixed_name_in_allowed_tools_tagged_correctly() -> None:
    cfg = Commission(
        schema_version="0.1",
        run_id="with-mcp",
        model="claude-sonnet-4-6",
        prompt="hi",
        allowed_tools=["Read", "mcp__weather__forecast"],
    )
    t, out = _new_translator(cfg)
    t._emit_agent_started()
    tools = _agent_started(out).data.tools
    assert tools is not None
    by_name = {tool.name: tool for tool in tools}
    assert by_name["mcp__weather__forecast"].avp_dispatch_target == "mcp_server"
    wire = _agent_started(out).model_dump(mode="json", by_alias=True, exclude_none=True)
    mcp_decl = next(t for t in wire["data"]["tools"] if t["name"] == "mcp__weather__forecast")
    assert mcp_decl["avp.mcp_server_id"] == "weather"
