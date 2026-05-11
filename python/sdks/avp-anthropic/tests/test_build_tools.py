"""Tests for `build_anthropic_tools`: the one place where AVP Commission
translates to Anthropic's `tools[]` parameter for the Messages API.

Reference agents and any direct AVPAgent caller go through this helper. In
the refs-only Commission model, the helper returns the agent's built-in
tool catalog, optionally filtered by `Commission.enabled_builtin_tools`.
Managed assets (`Commission.{mcp_servers,subagents}` refs) are surfaced
via the resolver protocol and merged into `tools_param` by
`AnthropicModelDriver.set_resolved_assets`; this helper does not touch them.
"""

from __future__ import annotations

from avp import Commission
from avp_anthropic import build_anthropic_tools


def _names(tools: list[dict]) -> list[str]:
    return [t["name"] for t in tools]


def test_returns_empty_when_no_builtins() -> None:
    cfg = Commission(schema_version="0.1", run_id="r")
    assert build_anthropic_tools(cfg) == []


def test_passes_builtins_through_unchanged() -> None:
    """Without an allowlist, every supplied built-in surfaces in order."""
    cfg = Commission(schema_version="0.1", run_id="r")
    builtins = [
        {"name": "bash", "description": "Run shell.", "input_schema": {"type": "object"}},
        {"name": "read_file", "description": "Read a file.", "input_schema": {"type": "object"}},
    ]
    out = build_anthropic_tools(cfg, builtins=builtins)
    assert _names(out) == ["bash", "read_file"]


def test_enabled_builtin_tools_filters_builtins_in_declared_order() -> None:
    """`Commission.enabled_builtin_tools` restricts the model-visible set to
    the listed names. Names not in the list drop out."""
    cfg = Commission(
        schema_version="0.1",
        run_id="r",
        enabled_builtin_tools=["read_file"],
    )
    builtins = [
        {"name": "bash", "input_schema": {"type": "object"}},
        {"name": "read_file", "input_schema": {"type": "object"}},
    ]
    out = build_anthropic_tools(cfg, builtins=builtins)
    assert _names(out) == ["read_file"]


def test_enabled_builtin_tools_empty_returns_empty_list() -> None:
    """An explicit empty allowlist hides every built-in (a deliberate
    'no built-ins this run' Commission)."""
    cfg = Commission(
        schema_version="0.1",
        run_id="r",
        enabled_builtin_tools=[],
    )
    builtins = [
        {"name": "bash", "input_schema": {"type": "object"}},
        {"name": "read_file", "input_schema": {"type": "object"}},
    ]
    out = build_anthropic_tools(cfg, builtins=builtins)
    assert out == []


def test_enabled_builtin_tools_unset_means_all_builtins() -> None:
    """`enabled_builtin_tools=None` (absent) means 'no allowlist; all
    builtins surface.' Backwards-compatible with the no-Commission case."""
    cfg = Commission(schema_version="0.1", run_id="r")
    builtins = [{"name": "bash", "input_schema": {}}]
    out = build_anthropic_tools(cfg, builtins=builtins)
    assert _names(out) == ["bash"]
