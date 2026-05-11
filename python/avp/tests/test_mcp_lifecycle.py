"""MCP server lifecycle: when Commission.mcp_servers is non-empty, the agent
MUST resolve each ref via avp.resolve at startup, emit one
mcp_server_connected per server before the first model turn, and one
mcp_server_disconnected per server before agent_stopped.

The reference agent ships v0.1 with stub event emission (no real `initialize`
/ `tools/list` over the transport); the live transport is a separable concern
landing in a follow-up once the optional `mcp` Python SDK or HTTP client is
plumbed in.
"""

from __future__ import annotations

from avp import AgentDescriptor, Commission, McpServerRef
from avp.agent.agent import AVPAgent
from avp.agent.drivers import ModelResponse
from avp.agent.mock import (
    ScriptedModel,
    ScriptedResolver,
    ScriptedSupervisor,
    ScriptedTools,
)
from avp.types import McpServerConnectedEvent, McpServerDisconnectedEvent


def _trivial_model() -> ScriptedModel:
    return ScriptedModel(
        [
            ModelResponse(
                tokens_input=1,
                tokens_output=1,
                cost_usd=0.001,
                duration_ms=1,
                text="ok",
                converged=True,
            ),
        ]
    )


def _managed_descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        agent_name="test-agent",
        agent_version="0.0.0",
        avp_spec_version="0.1",
    )


def test_no_mcp_servers_emits_no_lifecycle_events() -> None:
    commission = Commission(schema_version="0.1", run_id="r-no-mcp", prompt="hi")
    agent = AVPAgent(commission, _trivial_model(), ScriptedTools(), ScriptedSupervisor())
    agent.run()
    types = [ev.type for ev in agent.trajectory]
    assert "avp.mcp_server_connected" not in types
    assert "avp.mcp_server_disconnected" not in types


def test_mcp_servers_emit_connect_then_disconnect_in_order() -> None:
    commission = Commission(
        schema_version="0.1",
        run_id="r-mcp-pair",
        prompt="hi",
        mcp_servers=[
            McpServerRef(id="github", ref={"vault": "test", "key": "gh"}),
            McpServerRef(id="fs", ref="vault://fs-mcp"),
        ],
    )
    resolver = ScriptedResolver(
        resolutions={
            "mcp_server:github": {"result": {"transport": "http", "url": "https://x/gh"}},
            "mcp_server:fs": {"result": {"transport": "stdio", "command": ["fs"]}},
        }
    )
    agent = AVPAgent(
        commission,
        _trivial_model(),
        ScriptedTools(),
        ScriptedSupervisor(),
        resolver=resolver,
        descriptor=_managed_descriptor(),
    )
    agent.run()

    types = [ev.type for ev in agent.trajectory]

    # Connect events fire after agent_started + each ref's managed_ref_resolved,
    # before model_turn_started.
    started_idx = types.index("avp.agent_started")
    first_turn_idx = types.index("avp.model_turn_started")
    connect_idxs = [i for i, t in enumerate(types) if t == "avp.mcp_server_connected"]
    assert len(connect_idxs) == 2
    assert all(started_idx < i < first_turn_idx for i in connect_idxs)

    # Disconnect events fire before agent_stopped.
    stopped_idx = types.index("avp.agent_stopped")
    disconnect_idxs = [i for i, t in enumerate(types) if t == "avp.mcp_server_disconnected"]
    assert len(disconnect_idxs) == 2
    assert all(i < stopped_idx for i in disconnect_idxs)

    # Connected events carry the server id and a protocol version.
    connected = [ev for ev in agent.trajectory if isinstance(ev, McpServerConnectedEvent)]
    server_ids = sorted(ev.data.avp_mcp_server_id for ev in connected)
    assert server_ids == ["fs", "github"]
    for ev in connected:
        assert ev.data.avp_mcp_protocol_version == "2025-11-25"

    # Disconnect events carry the same ids and a clean reason.
    disconnected = [ev for ev in agent.trajectory if isinstance(ev, McpServerDisconnectedEvent)]
    assert sorted(ev.data.avp_mcp_server_id for ev in disconnected) == ["fs", "github"]
    for ev in disconnected:
        assert ev.data.avp_mcp_disconnect_reason == "clean"


def test_managed_ref_resolve_failed_short_circuits_before_mcp_connect() -> None:
    """When a Commission.mcp_servers ref fails to resolve, the agent emits
    managed_ref_resolve_failed and stops before any mcp_server_connected
    fires — the resolver gate runs ahead of the connection attempt."""
    commission = Commission(
        schema_version="0.1",
        run_id="r-mcp-resolve-fail",
        prompt="hi",
        mcp_servers=[McpServerRef(id="github", ref="bad-ref")],
    )
    resolver = ScriptedResolver(
        resolutions={"mcp_server:github": {"error": "not found", "error_code": "not_found"}}
    )
    agent = AVPAgent(
        commission,
        _trivial_model(),
        ScriptedTools(),
        ScriptedSupervisor(),
        resolver=resolver,
        descriptor=_managed_descriptor(),
    )
    agent.run()

    types = [ev.type for ev in agent.trajectory]
    assert "avp.managed_ref_resolve_failed" in types
    assert "avp.mcp_server_connected" not in types
    assert "avp.model_turn_started" not in types
    assert types[-1] == "avp.agent_stopped"
