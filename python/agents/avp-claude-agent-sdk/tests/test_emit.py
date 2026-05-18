"""Stage 1 unit tests: drive the prelude emitters + `handle_message`
directly against a recording sink. Faster + simpler than spinning up the
CLI; verifies prelude split (phase A in connect, phase B on init),
filtering of non-connected MCP servers, mcp__-prefix filter on init
tools, merge gate, per-turn deltas, content translation, empty-output
gate, and agent_stopped reason mapping.
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any

from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    McpStatusResponse,
    TextBlock,
    ThinkingBlock,
)

from avp._envelope import new_trace_id
from avp.pricing import load_default_prices
from avp.trajectory import Event
from avp_claude_agent_sdk._emit import (
    emit_agent_described,
    emit_agent_started,
    emit_run_requested,
    handle_message,
)
from avp_claude_agent_sdk._runstate import RunState

# ---------------------------------------------------------------------------
# Stand-in SDK message types whose class names match the dispatch strings.
# Use these instead of the real SDK dataclasses when we want to control
# specific fields without invoking the full SDK constructor.
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ToolResultBlock:
    tool_use_id: str = "toolu_01"
    content: str = "ok"
    is_error: bool = False


@dataclasses.dataclass
class UserMessage:
    content: list[Any] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ResultMessage:
    result: str | None = "done"
    is_error: bool = False
    stop_reason: str | None = "end_turn"


@dataclasses.dataclass
class SystemMessage:
    """Mimics `claude_agent_sdk.types.SystemMessage`: dispatcher uses
    class-name + `subtype` so this stand-in is sufficient for tests."""

    subtype: str
    data: dict[str, Any] = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(events: list[Event]) -> RunState:
    async def sink(event: Event) -> None:
        events.append(event)

    return RunState(
        trace_id=new_trace_id(),
        run_id="test-run",
        sink=sink,
        prices=load_default_prices(),
    )


def _assistant(
    *blocks: Any,
    model: str = "claude-haiku-4-5-20251001",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
    stop_reason: str | None = None,
) -> AssistantMessage:
    """AssistantMessage with a stubbed usage dict (cumulative-form)."""
    usage = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_creation,
    }
    return AssistantMessage(
        content=list(blocks),
        model=model,
        usage=usage,
        stop_reason=stop_reason,
    )


def _user_tool_result() -> UserMessage:
    return UserMessage(content=[ToolResultBlock()])


def _status(
    *, connected_named: str | None = "demo", extra_pending: bool = False
) -> McpStatusResponse:
    """Build an `McpStatusResponse`. `connected_named` adds one
    `connected` server with the given name; `extra_pending` adds a
    second server in `needs-auth` that the descriptor MUST filter out.
    """
    servers: list[dict[str, Any]] = []
    if connected_named:
        servers.append(
            {
                "name": connected_named,
                "status": "connected",
                "config": {"id": "mcpsrv_demo"},
                "tools": [{"name": "search"}],
            }
        )
    if extra_pending:
        servers.append(
            {
                "name": "claude.ai Gmail",
                "status": "needs-auth",
                "config": {"id": "mcpsrv_gmail"},
            }
        )
    return McpStatusResponse(mcpServers=servers)


def _init(
    *,
    tools: list[str] | None = None,
    model: str = "claude-haiku-4-5-20251001",
    agents: list[str] | None = None,
    skills: list[str] | None = None,
) -> SystemMessage:
    return SystemMessage(
        subtype="init",
        data={
            "tools": tools or [],
            "model": model,
            "agents": agents or [],
            "skills": skills or [],
        },
    )


async def _drive_prelude(
    *,
    init: SystemMessage | None,
    status: McpStatusResponse | None = None,
    prompt: str = "ping",
    model: str | None = "claude-haiku-4-5-20251001",
) -> list[Event]:
    """Run the full prelude (`run_requested` + `agent_described` +
    `agent_started`) and return recorded events. `init=None` simulates a
    failed probe so the descriptor falls back to identity-only."""
    events: list[Event] = []
    state = _make_state(events)
    options = ClaudeAgentOptions(model=model) if model else ClaudeAgentOptions()
    eff_status = status if status is not None else _status()
    init_data = init.data if init is not None else None
    await emit_run_requested(state)
    await emit_agent_described(
        state, options, prompt=prompt, init_data=init_data, status=eff_status
    )
    await emit_agent_started(
        state,
        prompt=prompt,
        options=options,
        init_data=init_data,
        status=eff_status,
    )
    return events


async def _drive(
    messages: list[Any],
    *,
    prompt: str = "ping",
    model: str = "claude-haiku-4-5-20251001",
    status: McpStatusResponse | None = None,
    init: SystemMessage | None = None,
) -> list[Event]:
    """Run the full prelude then dispatch each message; return events."""
    events: list[Event] = []
    state = _make_state(events)
    options = ClaudeAgentOptions(model=model)
    eff_status = status if status is not None else _status()
    eff_init = init if init is not None else _init(model=model)
    init_data = eff_init.data
    await emit_run_requested(state)
    await emit_agent_described(
        state, options, prompt=prompt, init_data=init_data, status=eff_status
    )
    await emit_agent_started(
        state,
        prompt=prompt,
        options=options,
        init_data=init_data,
        status=eff_status,
    )
    for msg in messages:
        await handle_message(state, msg)
    return events


# ---------------------------------------------------------------------------
# Prelude
# ---------------------------------------------------------------------------


def test_prelude_order_is_run_requested_described_started() -> None:
    """Spec §2.1: the prelude head MUST be
    run_requested → agent_described → agent_started, in that order."""
    events = asyncio.run(_drive_prelude(init=_init(tools=["Bash"])))
    types = [ev.type for ev in events]
    assert types == ["avp.run_requested", "avp.agent_described", "avp.agent_started"]
    assert len({ev.data.trace_id for ev in events}) == 1
    ZERO = "0" * 16
    for ev in events:
        assert ev.data.parent_span_id == ZERO


def test_agent_described_carries_full_pre_commission_surface() -> None:
    """`agent_described` is built from the probe session: the agent's
    full capabilities BEFORE any Commission filter applies."""
    events = asyncio.run(
        _drive_prelude(
            init=_init(
                tools=["Bash", "Read", "Edit", "mcp__demo__search"],
                agents=["Explore", "Plan"],
                skills=["xlsx", "review"],
            ),
        )
    )
    described = next(ev for ev in events if ev.type == "avp.agent_described")
    desc = described.data.descriptor
    assert desc.agent_name == "avp-claude-agent-sdk"
    # mcp__-prefixed tools are filtered out (they live on
    # mcp_server_connected events instead, per spec §8).
    assert [t.name for t in desc.tools] == ["Bash", "Read", "Edit"]
    assert [a.name for a in desc.subagents] == ["Explore", "Plan"]
    assert [s.name for s in desc.skills] == ["xlsx", "review"]


def test_agent_started_mirrors_descriptor_when_no_commission() -> None:
    """Without a Commission, `agent_started` is the same surface as
    `agent_described` (no merge to do). Stage 3 will add Commission
    filters that produce a strict subset on `agent_started`."""
    events = asyncio.run(
        _drive_prelude(
            init=_init(
                tools=["Bash", "Read", "mcp__demo__search"],
                agents=["Explore"],
                skills=["xlsx"],
            ),
        )
    )
    described = next(ev for ev in events if ev.type == "avp.agent_described")
    started = next(ev for ev in events if ev.type == "avp.agent_started")
    assert [t.name for t in started.data.tools] == [t.name for t in described.data.descriptor.tools]
    assert [a.name for a in started.data.subagents] == [
        a.name for a in described.data.descriptor.subagents
    ]
    assert [s.name for s in started.data.skills] == [
        s.name for s in described.data.descriptor.skills
    ]
    assert [s.id for s in started.data.mcp_servers] == [
        s.id for s in described.data.descriptor.mcp_servers
    ]


def test_request_model_prefers_init_resolved_model() -> None:
    """init.model is the SDK's server-side resolved model; it overrides
    options.model when present."""
    events = asyncio.run(
        _drive_prelude(
            init=_init(model="claude-opus-4-7[1m]"),
            model="claude-haiku-4-5-20251001",
        )
    )
    started = next(ev for ev in events if ev.type == "avp.agent_started")
    assert started.data.request_model == "claude-opus-4-7[1m]"


def test_non_connected_mcp_servers_are_filtered_out() -> None:
    """needs-auth / failed / disabled / pending servers MUST NOT appear
    on agent_started or agent_described (spec §2.1: 'what is currently
    available' means usable, not configured-but-unauth'd)."""
    events = asyncio.run(
        _drive_prelude(
            init=_init(),
            status=_status(connected_named="demo", extra_pending=True),
        )
    )
    started = next(ev for ev in events if ev.type == "avp.agent_started")
    described = next(ev for ev in events if ev.type == "avp.agent_described")
    assert [s.id for s in started.data.mcp_servers] == ["mcpsrv_demo"]
    assert [s.id for s in described.data.descriptor.mcp_servers] == ["mcpsrv_demo"]


def test_prelude_falls_back_when_probe_failed() -> None:
    """If the probe pass failed (init never arrived), the descriptor
    falls back to identity + default_model and the prelude is still
    conformant."""
    events = asyncio.run(_drive_prelude(init=None))
    types = [ev.type for ev in events]
    assert types == ["avp.run_requested", "avp.agent_described", "avp.agent_started"]
    desc = events[1].data.descriptor
    assert desc.tools is None
    assert desc.subagents is None
    assert desc.skills is None
    started = events[2]
    assert started.data.tools is None
    assert started.data.subagents is None
    assert started.data.skills is None


# ---------------------------------------------------------------------------
# Single-turn assistant_message
# ---------------------------------------------------------------------------


def test_assistant_message_emits_on_result_with_content_and_usage() -> None:
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    TextBlock(text="hello"),
                    output_tokens=5,
                    input_tokens=10,
                    stop_reason="end_turn",
                ),
                ResultMessage(result="done"),
            ]
        )
    )
    types = [ev.type for ev in events]
    assert "avp.assistant_message" in types
    assert types[-1] == "avp.agent_stopped"

    msg = next(ev for ev in events if ev.type == "avp.assistant_message")
    assert msg.data.step == 1
    assert msg.data.parent_span_id == events[2].data.span_id  # under agent span
    assert [b.type for b in msg.data.content] == ["text"]
    assert msg.data.content[0].text == "hello"
    assert msg.data.usage.input_tokens == 10
    assert msg.data.usage.output_tokens == 5
    assert msg.data.response_finish_reasons == ["end_turn"]
    assert msg.data.response_model == "claude-haiku-4-5-20251001"


def test_thinking_block_translates_to_avp_thinking() -> None:
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ThinkingBlock(thinking="ponder", signature="sig"),
                    TextBlock(text="answer"),
                    output_tokens=8,
                    input_tokens=4,
                ),
                ResultMessage(),
            ]
        )
    )
    msg = next(ev for ev in events if ev.type == "avp.assistant_message")
    kinds = [b.type for b in msg.data.content]
    assert kinds == ["thinking", "text"]
    assert msg.data.content[0].thinking == "ponder"
    assert msg.data.content[0].signature == "sig"


# ---------------------------------------------------------------------------
# Merge gate + turn boundaries
# ---------------------------------------------------------------------------


def test_consecutive_assistant_messages_merge_into_one_turn() -> None:
    """Thinking-only msg followed by text msg with no tool result between
    them = the same LLM call. One assistant_message, content is the union."""
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ThinkingBlock(thinking="think", signature=""),
                    output_tokens=3,
                    input_tokens=4,
                ),
                _assistant(TextBlock(text="speak"), output_tokens=6, input_tokens=4),
                ResultMessage(),
            ]
        )
    )
    msgs = [ev for ev in events if ev.type == "avp.assistant_message"]
    assert len(msgs) == 1
    assert [b.type for b in msgs[0].data.content] == ["thinking", "text"]
    assert msgs[0].data.usage.input_tokens == 4
    assert msgs[0].data.usage.output_tokens == 6


def test_tool_result_boundary_opens_new_turn() -> None:
    events = asyncio.run(
        _drive(
            [
                _assistant(TextBlock(text="t1"), input_tokens=10, output_tokens=5),
                _user_tool_result(),
                _assistant(TextBlock(text="t2"), input_tokens=20, output_tokens=12),
                ResultMessage(),
            ]
        )
    )
    msgs = [ev for ev in events if ev.type == "avp.assistant_message"]
    assert len(msgs) == 2
    assert [m.data.step for m in msgs] == [1, 2]
    assert msgs[1].data.usage.input_tokens == 10
    assert msgs[1].data.usage.output_tokens == 7


# ---------------------------------------------------------------------------
# Empty-output gate
# ---------------------------------------------------------------------------


def test_empty_output_turn_is_not_emitted() -> None:
    events = asyncio.run(
        _drive(
            [
                _assistant(TextBlock(text=""), input_tokens=5, output_tokens=0),
                ResultMessage(),
            ]
        )
    )
    types = [ev.type for ev in events]
    assert "avp.assistant_message" not in types
    assert types[-1] == "avp.agent_stopped"


# ---------------------------------------------------------------------------
# agent_stopped reasons
# ---------------------------------------------------------------------------


def test_result_message_emits_agent_stopped_converged() -> None:
    events = asyncio.run(
        _drive(
            [
                _assistant(TextBlock(text="hi"), output_tokens=2, input_tokens=2),
                ResultMessage(result="done"),
            ]
        )
    )
    stopped = next(ev for ev in events if ev.type == "avp.agent_stopped")
    assert stopped.data.reason == "converged"
    assert stopped.data.output == "done"


def test_result_message_is_error_emits_error_reason() -> None:
    events = asyncio.run(_drive([ResultMessage(result=None, is_error=True, stop_reason="error")]))
    stopped = next(ev for ev in events if ev.type == "avp.agent_stopped")
    assert stopped.data.reason == "error"


def test_result_message_refusal_emits_refused_reason() -> None:
    events = asyncio.run(
        _drive([ResultMessage(result=None, is_error=False, stop_reason="refusal")])
    )
    stopped = next(ev for ev in events if ev.type == "avp.agent_stopped")
    assert stopped.data.reason == "refused"


def test_agent_stopped_is_idempotent() -> None:
    """ResultMessage handler fires once; a second call no-ops via state.stopped."""
    events = asyncio.run(_drive([ResultMessage(), ResultMessage()]))
    stops = [ev for ev in events if ev.type == "avp.agent_stopped"]
    assert len(stops) == 1


# ---------------------------------------------------------------------------
# Cumulative usage: silent rebase
# ---------------------------------------------------------------------------


def test_usage_silent_rebase_when_cum_drops() -> None:
    """When the SDK's cumulative counters drop (compaction), the next
    delta is computed against the new baseline, not the old one."""
    events = asyncio.run(
        _drive(
            [
                _assistant(TextBlock(text="t1"), input_tokens=100, output_tokens=50),
                _user_tool_result(),
                _assistant(TextBlock(text="t2"), input_tokens=10, output_tokens=7),
                ResultMessage(),
            ]
        )
    )
    msgs = [ev for ev in events if ev.type == "avp.assistant_message"]
    assert len(msgs) == 2
    assert msgs[1].data.usage.input_tokens == 10
    assert msgs[1].data.usage.output_tokens == 7
