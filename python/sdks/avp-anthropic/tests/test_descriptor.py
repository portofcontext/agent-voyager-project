"""Tests for `build_descriptor`: the avp-anthropic SDK's descriptor helper.

The SDK adapter doesn't ship a CLI or built-in tools. The helper produces
an `AgentDescriptor` for an agent that USES the SDK: the agent supplies
its own name, version, and tool catalog; the helper layers in the
SDK-side constants (hosted tool kinds, the `thinking` capability).
"""

from __future__ import annotations

from avp_anthropic import ANTHROPIC_HOSTED_TOOL_KINDS, build_descriptor


def test_minimal_descriptor_carries_sdk_capabilities_and_hosted_tools() -> None:
    """With no agent tools supplied, the Descriptor still records the
    things the SDK itself brings: hosted tool kinds + thinking
    capability."""
    d = build_descriptor(agent_name="my-agent", agent_version="0.1.0")
    assert d.agent_name == "my-agent"
    assert d.agent_version == "0.1.0"
    assert d.avp_spec_version == "0.1"
    assert d.supported_models == ["claude-*"]
    assert d.default_model is None

    # Driver-level capability: extended thinking blocks are parsed and
    # re-emitted as reasoning_emitted by AnthropicModelDriver.
    assert d.capabilities is not None
    assert "thinking" in d.capabilities

    # Hosted-tool block kinds the driver knows how to parse.
    assert d.built_in_tools is not None
    names = [t.name for t in d.built_in_tools]
    for hosted in ANTHROPIC_HOSTED_TOOL_KINDS:
        assert hosted in names


def test_agent_supplied_tools_round_trip_into_descriptor() -> None:
    """An agent author passes their tool catalog; it lands on the
    Descriptor with MCP-shaped `inputSchema` and a default
    `avp.dispatch_target="local"`."""
    tools = [
        {
            "name": "bash",
            "description": "Run a shell command.",
            # Anthropic API spelling; helper normalizes to camelCase.
            "input_schema": {
                "type": "object",
                "required": ["command"],
                "properties": {"command": {"type": "string"}},
            },
        },
        {
            "name": "fetch_url",
            "description": "HTTP GET.",
            "inputSchema": {"type": "object", "required": ["url"]},
        },
    ]
    d = build_descriptor(
        agent_name="my-agent",
        agent_version="0.1.0",
        built_in_tools=tools,
    )
    assert d.built_in_tools is not None
    by_name = {t.name: t for t in d.built_in_tools}
    assert "bash" in by_name
    assert "fetch_url" in by_name
    # Both spellings come out as MCP camelCase on the wire.
    assert by_name["bash"].inputSchema is not None
    assert by_name["fetch_url"].inputSchema is not None
    # Default dispatch target is local for agent-supplied tools.
    assert by_name["bash"].avp_dispatch_target == "local"


def test_disable_hosted_tools_when_agent_doesnt_opt_in() -> None:
    """Setting `include_hosted_tools=False` omits hosted tool kinds (the
    agent won't opt into web_search / code_execution at the API
    layer)."""
    d = build_descriptor(
        agent_name="my-agent",
        agent_version="0.1.0",
        built_in_tools=[
            {
                "name": "bash",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
        include_hosted_tools=False,
    )
    assert d.built_in_tools is not None
    names = [t.name for t in d.built_in_tools]
    assert "bash" in names
    for hosted in ANTHROPIC_HOSTED_TOOL_KINDS:
        assert hosted not in names


def test_agent_capabilities_merge_with_sdk_capabilities() -> None:
    """Extra capabilities passed by the agent appear alongside the SDK's
    `thinking`; duplicates are deduped."""
    d = build_descriptor(
        agent_name="my-agent",
        agent_version="0.1.0",
        capabilities=["mcp", "subagents", "thinking"],
    )
    assert d.capabilities is not None
    caps = list(d.capabilities)
    assert "thinking" in caps
    assert "mcp" in caps
    assert "subagents" in caps
    # No double-count even though the caller also listed thinking.
    assert caps.count("thinking") == 1


def test_supported_models_override() -> None:
    """An agent author can narrow `supported_models` (e.g. only haiku)."""
    d = build_descriptor(
        agent_name="my-agent",
        agent_version="0.1.0",
        supported_models=["claude-haiku-4-5-*"],
    )
    assert d.supported_models == ["claude-haiku-4-5-*"]
