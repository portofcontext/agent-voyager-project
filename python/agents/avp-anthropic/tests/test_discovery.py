"""Discovery API for Commission authoring (Anthropic agent side).

Symmetric in shape with the CASDK discovery, but narrower scope: no
filesystem walk because there's no Claude Code CLI subprocess. The
surface is just the agent's shell built-ins and the API-hosted tool
kinds the response parser knows about.
"""

from __future__ import annotations

from avp_anthropic import (
    ANTHROPIC_HOSTED_TOOL_KINDS,
    SHELL_TOOL_NAMES,
    SHELL_TOOL_SCHEMAS,
    Environment,
    discover_environment,
)


def test_shell_tool_names_re_exported() -> None:
    """`from avp_anthropic import SHELL_TOOL_NAMES` works for Commission
    authors who want to expose all shell built-ins via allowed_tools."""
    assert isinstance(SHELL_TOOL_NAMES, tuple)
    assert "bash" in SHELL_TOOL_NAMES
    assert "read_file" in SHELL_TOOL_NAMES
    assert "write_file" in SHELL_TOOL_NAMES


def test_shell_tool_names_matches_schemas() -> None:
    """SHELL_TOOL_NAMES is derived from SHELL_TOOL_SCHEMAS — they MUST
    stay in sync (one is the other projected to a tuple of names)."""
    assert set(SHELL_TOOL_NAMES) == {schema["name"] for schema in SHELL_TOOL_SCHEMAS}


def test_anthropic_hosted_tool_kinds_re_exported() -> None:
    assert isinstance(ANTHROPIC_HOSTED_TOOL_KINDS, tuple)
    assert "web_search" in ANTHROPIC_HOSTED_TOOL_KINDS
    assert "code_execution" in ANTHROPIC_HOSTED_TOOL_KINDS


def test_discover_environment_returns_constants() -> None:
    """No filesystem walk — discover_environment just wraps the
    constants in the same shape used by the CASDK side, so a supervisor
    can write one discovery helper that works across agents."""
    env = discover_environment()
    assert isinstance(env, Environment)
    assert env.shell_tools == SHELL_TOOL_NAMES
    assert env.anthropic_hosted_tools == ANTHROPIC_HOSTED_TOOL_KINDS


def test_environment_can_be_used_to_build_a_config() -> None:
    """Motivating use case: Commission author builds allowed_tools from
    discovered names, doesn't have to remember strings."""
    from avp import Commission

    env = discover_environment()
    cfg = Commission(
        schema_version="0.1",
        run_id="discovery-driven",
        model="claude-sonnet-4-6",
        prompt="hi",
        allowed_tools=list(env.shell_tools),
    )
    assert cfg.allowed_tools == ["bash", "read_file", "write_file"]
