"""MCP server lifecycle: when Commission.mcp_servers is non-empty, the agent MUST
emit one mcp_server_connected per server right after agent_started/skills_loaded
and one mcp_server_disconnected per server right before agent_stopped.

This pins the WIRE FORMAT for MCP integration. The reference agent ships v0.1
with stub event emission (no real `initialize` / `tools/list` over the
transport); the live transport is a separable concern landing in a follow-up
once the optional `mcp` Python SDK or HTTP client is plumbed in.
"""

from __future__ import annotations

from avp import Commission, McpServer
from avp.agent.agent import AVPAgent
from avp.agent.drivers import ModelResponse
from avp.agent.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
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


def test_no_mcp_servers_emits_no_lifecycle_events() -> None:
    commission = Commission(schema_version="0.1", run_id="r-no-mcp", prompt="hi", exposed=["*"])
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
            McpServer(id="github", transport="http", url="https://example.com/mcp"),
            McpServer(id="fs", transport="stdio", command=["npx", "mcp-server-fs"]),
        ],
        exposed=["*"],
    )
    agent = AVPAgent(commission, _trivial_model(), ScriptedTools(), ScriptedSupervisor())
    agent.run()

    types = [ev.type for ev in agent.trajectory]

    # Connect events fire after agent_started, before model_turn_started.
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


def test_mcp_disconnect_fires_even_when_run_errors_at_validation() -> None:
    """If the agent errors during validation (e.g. allowed_tools cross-check
    fails), it still MUST disconnect any MCP servers it announced. The
    lifecycle is symmetric: every connected event has a matching disconnected."""
    from avp import Subagent

    commission = Commission(
        schema_version="0.1",
        run_id="r-mcp-err",
        prompt="hi",
        # Subagent declared but missing from allowed_tools — the agent
        # flags this at startup and stops with reason=error.
        subagents=[Subagent(name="missing", description="x", exposed=["*"])],
        exposed=["other"],
        mcp_servers=[McpServer(id="github", transport="http", url="https://x/mcp")],
    )
    agent = AVPAgent(commission, _trivial_model(), ScriptedTools(), ScriptedSupervisor())
    agent.run()

    types = [ev.type for ev in agent.trajectory]
    assert "avp.mcp_server_connected" in types
    assert "avp.mcp_server_disconnected" in types
    # Ordering: connect → error → disconnect → agent_stopped
    assert types.index("avp.mcp_server_connected") < types.index("avp.error_occurred")
    assert types.index("avp.mcp_server_disconnected") < types.index("avp.agent_stopped")
