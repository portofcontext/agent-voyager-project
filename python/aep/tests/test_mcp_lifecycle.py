"""MCP server lifecycle: when Config.mcp_servers is non-empty, the runner MUST
emit one mcp_server_connected per server right after agent_started/skills_loaded
and one mcp_server_disconnected per server right before agent_stopped.

This pins the WIRE FORMAT for MCP integration. The reference runner ships v0.1
with stub event emission (no real `initialize` / `tools/list` over the
transport); the live transport is a separable concern landing in a follow-up
once the optional `mcp` Python SDK or HTTP client is plumbed in.
"""

from __future__ import annotations

from aep import Config, McpServer
from aep.runner.drivers import ModelResponse
from aep.runner.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from aep.runner.runner import AEPRunner
from aep.types import McpServerConnectedEvent, McpServerDisconnectedEvent


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
    cfg = Config(schema_version="0.1", run_id="r-no-mcp", prompt="hi")
    runner = AEPRunner(cfg, _trivial_model(), ScriptedTools(), ScriptedSupervisor())
    runner.run()
    types = [ev.type for ev in runner.trajectory]
    assert "aep.mcp_server_connected" not in types
    assert "aep.mcp_server_disconnected" not in types


def test_mcp_servers_emit_connect_then_disconnect_in_order() -> None:
    cfg = Config(
        schema_version="0.1",
        run_id="r-mcp-pair",
        prompt="hi",
        mcp_servers=[
            McpServer(id="github", transport="http", url="https://example.com/mcp"),
            McpServer(id="fs", transport="stdio", command=["npx", "mcp-server-fs"]),
        ],
    )
    runner = AEPRunner(cfg, _trivial_model(), ScriptedTools(), ScriptedSupervisor())
    runner.run()

    types = [ev.type for ev in runner.trajectory]

    # Connect events fire after agent_started, before model_turn_started.
    started_idx = types.index("aep.agent_started")
    first_turn_idx = types.index("aep.model_turn_started")
    connect_idxs = [i for i, t in enumerate(types) if t == "aep.mcp_server_connected"]
    assert len(connect_idxs) == 2
    assert all(started_idx < i < first_turn_idx for i in connect_idxs)

    # Disconnect events fire before agent_stopped.
    stopped_idx = types.index("aep.agent_stopped")
    disconnect_idxs = [i for i, t in enumerate(types) if t == "aep.mcp_server_disconnected"]
    assert len(disconnect_idxs) == 2
    assert all(i < stopped_idx for i in disconnect_idxs)

    # Connected events carry the server id and a protocol version.
    connected = [ev for ev in runner.trajectory if isinstance(ev, McpServerConnectedEvent)]
    server_ids = sorted(ev.data.aep_mcp_server_id for ev in connected)
    assert server_ids == ["fs", "github"]
    for ev in connected:
        assert ev.data.aep_mcp_protocol_version == "2025-11-25"

    # Disconnect events carry the same ids and a clean reason.
    disconnected = [ev for ev in runner.trajectory if isinstance(ev, McpServerDisconnectedEvent)]
    assert sorted(ev.data.aep_mcp_server_id for ev in disconnected) == ["fs", "github"]
    for ev in disconnected:
        assert ev.data.aep_mcp_disconnect_reason == "clean"


def test_mcp_disconnect_fires_even_when_run_errors_at_validation() -> None:
    """If the runner errors during validation (e.g. allowed_tools cross-check
    fails), it still MUST disconnect any MCP servers it announced. The
    lifecycle is symmetric: every connected event has a matching disconnected."""
    cfg = Config(
        schema_version="0.1",
        run_id="r-mcp-err",
        prompt="hi",
        # Construct a config where an entry in `tools` is missing from `allowed_tools`,
        # which the runner flags as a validation error and stops with reason=error.
        tools=[{"name": "missing", "inputSchema": {"type": "object"}}],
        allowed_tools=["other"],
        mcp_servers=[McpServer(id="github", transport="http", url="https://x/mcp")],
    )
    runner = AEPRunner(cfg, _trivial_model(), ScriptedTools(), ScriptedSupervisor())
    runner.run()

    types = [ev.type for ev in runner.trajectory]
    assert "aep.mcp_server_connected" in types
    assert "aep.mcp_server_disconnected" in types
    # Ordering: connect → error → disconnect → agent_stopped
    assert types.index("aep.mcp_server_connected") < types.index("aep.error_occurred")
    assert types.index("aep.mcp_server_disconnected") < types.index("aep.agent_stopped")
