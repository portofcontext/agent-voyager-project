"""Tests for build_anthropic_tools — the one place AVP Commission translates to
Anthropic's tools[] parameter shape.

The CLI and any direct AVPAgent caller (in-process supervisor, real-LLM
test) MUST go through this helper or they'll disagree on what's exposed
to the model. These tests pin the merge order, the inputSchema rename,
the subagent default schema, and the allowed_tools filter.
"""

from __future__ import annotations

from avp import Commission, Subagent
from avp_anthropic import build_anthropic_tools


def _names(tools: list[dict]) -> list[str]:
    return [t["name"] for t in tools]


def test_returns_empty_when_config_has_no_subagents_and_no_builtins() -> None:
    cfg = Commission(schema_version="0.1", run_id="r")
    assert build_anthropic_tools(cfg) == []


def test_includes_builtins_first_then_subagents() -> None:
    """Merge order matters for the model's tool list — builtins (the
    agent's always-on capabilities) come first."""
    cfg = Commission(
        schema_version="0.1",
        run_id="r",
        subagents=[Subagent(name="planner", description="Decomposes work.")],
    )
    builtins = [
        {"name": "bash", "description": "Run a shell command.", "input_schema": {"type": "object"}}
    ]
    out = build_anthropic_tools(cfg, builtins=builtins)
    assert _names(out) == ["bash", "planner"]


def test_subagent_with_no_inputSchema_gets_prompt_default() -> None:
    """Default subagent inputSchema is `{prompt: string}` — matches
    Claude Agent SDK's `Agent` tool shape and DeepAgents' `task` tool."""
    cfg = Commission(
        schema_version="0.1",
        run_id="r",
        subagents=[Subagent(name="helper", description="Helps with stuff.")],
    )
    out = build_anthropic_tools(cfg)
    assert len(out) == 1
    schema = out[0]["input_schema"]
    assert schema["type"] == "object"
    assert "prompt" in schema["properties"]
    assert schema["properties"]["prompt"]["type"] == "string"
    assert schema["required"] == ["prompt"]


def test_subagent_with_explicit_inputSchema_uses_it() -> None:
    custom = {
        "type": "object",
        "properties": {"target": {"type": "string"}, "depth": {"type": "integer"}},
        "required": ["target"],
    }
    cfg = Commission(
        schema_version="0.1",
        run_id="r",
        subagents=[Subagent(name="explorer", description="Walks a tree.", inputSchema=custom)],
    )
    out = build_anthropic_tools(cfg)
    assert out[0]["input_schema"] == custom


def test_allowed_tools_filters_after_merge() -> None:
    """Allowed_tools is the model-visible allowlist — applies to builtins
    and Commission.subagents uniformly. Anything not listed drops out,
    including builtins."""
    cfg = Commission(
        schema_version="0.1",
        run_id="r",
        subagents=[
            Subagent(name="planner", description="."),
            Subagent(name="reviewer", description="."),
        ],
        allowed_tools=["planner"],  # `bash` and `reviewer` should drop
    )
    builtins = [{"name": "bash", "input_schema": {"type": "object"}}]
    out = build_anthropic_tools(cfg, builtins=builtins)
    assert _names(out) == ["planner"]


def test_no_allowed_tools_means_no_filter() -> None:
    cfg = Commission(
        schema_version="0.1",
        run_id="r",
        subagents=[Subagent(name="x", description=".")],
    )
    out = build_anthropic_tools(cfg, builtins=[{"name": "bash", "input_schema": {}}])
    assert _names(out) == ["bash", "x"]
