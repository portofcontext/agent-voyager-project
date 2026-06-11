"""Unit tests: drive the prelude emitters + `handle_message` directly
against a recording sink. Faster + simpler than spinning up the CLI;
verifies prelude split (part in connect, part on init), filtering
of non-connected MCP servers, mcp__-prefix filter on init tools,
message_id-driven turn merging, per-call usage, content translation,
empty-output gate, and agent_stopped reason mapping.
"""

from __future__ import annotations

import asyncio
from typing import Any

from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    McpStatusResponse,
    ResultMessage,
    ServerToolResultBlock,
    ServerToolUseBlock,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from avp.envelope import new_trace_id
from avp.pricing import load_default_prices
from avp.trajectory import Event
from avp_claude_agent_sdk._emit import (
    context_usage_meta,
    emit_agent_described,
    emit_agent_started,
    emit_run_requested,
    handle_message,
)
from avp_claude_agent_sdk._runstate import RunState

# ---------------------------------------------------------------------------
# Fixture builders. `_result()` fills the six required ResultMessage fields
# with sensible defaults so tests can override just the bits they care about.
# ---------------------------------------------------------------------------


def _result(
    *,
    result: str | None = "done",
    is_error: bool = False,
    stop_reason: str | None = "end_turn",
) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=0,
        duration_api_ms=0,
        is_error=is_error,
        num_turns=0,
        session_id="test-session",
        stop_reason=stop_reason,
        result=result,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(events: list[Event], *, prompt: str | None = "ping") -> RunState:
    async def sink(event: Event) -> None:
        events.append(event)

    return RunState(
        trace_id=new_trace_id(),
        run_id="test-run",
        sink=sink,
        prices=load_default_prices(),
        prompt=prompt,
    )


def _assistant(
    *blocks: Any,
    model: str = "claude-haiku-4-5-20251001",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
    stop_reason: str | None = None,
    message_id: str | None = None,
) -> AssistantMessage:
    """AssistantMessage with a stubbed usage dict.

    Usage is the API call's response total for the inference identified
    by `message_id`, mirroring the SDK contract (every chunk of one
    `message_id` carries the same totals; a different `message_id`
    reports its own totals — there's no cumulative-across-session
    counter on the wire). Leave `message_id=None` for single-chunk
    fixtures where the inference identity doesn't matter to the test.
    """
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
        message_id=message_id,
    )


def _user_tool_result(
    tool_use_id: str = "toolu_01",
    content: str = "ok",
    is_error: bool | None = None,
) -> UserMessage:
    return UserMessage(
        content=[ToolResultBlock(tool_use_id=tool_use_id, content=content, is_error=is_error)]
    )


def _status(
    *, connected_named: str | None = "demo", extra_pending: bool = False
) -> McpStatusResponse:
    """Build an `McpStatusResponse`. `connected_named` adds one
    `connected` server; `extra_pending` adds a second server in
    `needs-auth` which (per AVP v0.1) is recorded on the wire with
    `status: "needs-auth"` rather than filtered out.
    """
    servers: list[dict[str, Any]] = []
    if connected_named:
        servers.append(
            {
                "name": connected_named,
                "status": "connected",
                "config": {"id": "mcpsrv_demo"},
                "tools": [{"name": "search", "description": "Search the demo index."}],
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
        # `client` is only consumed by `_on_system_init` (SystemMessage
        # path), and these tests prime the prelude separately rather
        # than dispatching SystemMessage through `handle_message`.
        await handle_message(None, state, msg)  # type: ignore[arg-type]
    # The real lifecycle drains via `_on_result` (and `_client.disconnect`)
    # at end-of-stream; `handle_message` doesn't currently route
    # ResultMessage, so drain here to flush any buffered emissions for
    # the test's open turn.
    if state.turn is not None:
        await state.drain()
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


def test_apply_enabled_builtin_tools_filters_the_bag() -> None:
    """The enabled_builtin_tools allow-list filters agent_started's tool bag:
    None passes through (all), [] yields [] (none), a list keeps only the named
    tools, and [] yields [] even when the bag was None."""
    from avp.descriptor import ToolDecl
    from avp_claude_agent_sdk._emit import _apply_enabled_builtin_tools

    bag = [ToolDecl(name="Bash"), ToolDecl(name="Read"), ToolDecl(name="mcp__x__y")]
    assert _apply_enabled_builtin_tools(bag, None) == bag
    assert _apply_enabled_builtin_tools(bag, []) == []
    assert [t.name for t in _apply_enabled_builtin_tools(bag, ["Bash"])] == ["Bash"]
    assert _apply_enabled_builtin_tools(None, []) == []
    assert _apply_enabled_builtin_tools(None, None) is None


def test_client_normalizes_missing_options() -> None:
    """Constructing the client without explicit `options` (as the Commission-
    driven conformance `run` does) must not leave `_original_options` as None:
    the probe + descriptor translation read `options.system_prompt` etc. and
    would crash on None. Regression for the conformance `run` path."""
    from claude_agent_sdk.types import ClaudeAgentOptions

    from avp.commission import Commission
    from avp_claude_agent_sdk import AVPClaudeSDKClient

    client = AVPClaudeSDKClient(
        commission=Commission(
            schema_version="0.1", run_id="x", model="anthropic/claude-haiku-4-5-20251001"
        )
    )
    assert isinstance(client._original_options, ClaudeAgentOptions)


def test_inline_skill_is_materialized_to_disk_and_named(tmp_path) -> None:
    """An inline Commission skill must reach the agent: its files written under
    `<cwd>/.claude/skills/<id>/` (where the CLI discovers project skills) AND its
    name passed in `options.skills`. Regression: the onboarding eval showed
    claude-code answering cold because inline skills were dropped entirely."""
    from claude_agent_sdk.types import ClaudeAgentOptions

    from avp.commission import Commission
    from avp_claude_agent_sdk._commission import apply_commission

    commission = Commission(
        schema_version="0.1",
        run_id="x",
        model="anthropic/claude-haiku-4-5",
        skills=[{"id": "avp", "files": {"SKILL.md": "---\nname: avp\n---\nbody", "ref.md": "x"}}],
    )
    options = apply_commission(commission, ClaudeAgentOptions(cwd=str(tmp_path)))

    skill_md = tmp_path / ".claude" / "skills" / "avp" / "SKILL.md"
    assert skill_md.read_text() == "---\nname: avp\n---\nbody"
    assert (tmp_path / ".claude" / "skills" / "avp" / "ref.md").read_text() == "x"
    assert options.skills == ["avp"]  # frontmatter name, passed as the SDK filter
    # The materialized skill is a PROJECT skill; it loads only if setting_sources
    # includes "project". Must be added even when the caller isolated with [].
    assert "project" in (options.setting_sources or [])


def test_inline_skill_adds_project_to_isolated_setting_sources(tmp_path) -> None:
    """A caller that isolates with setting_sources=[] (the conformance run does)
    must still get "project" added so the materialized skill is discovered — but
    not "user" (which would re-inherit the host ~/.claude it isolated from)."""
    from claude_agent_sdk.types import ClaudeAgentOptions

    from avp.commission import Commission
    from avp_claude_agent_sdk._commission import apply_commission

    commission = Commission(
        schema_version="0.1",
        run_id="x",
        model="anthropic/claude-haiku-4-5",
        skills=[{"id": "avp", "files": {"SKILL.md": "---\nname: avp\n---\nbody"}}],
    )
    options = apply_commission(
        commission, ClaudeAgentOptions(cwd=str(tmp_path), setting_sources=[])
    )
    assert options.setting_sources == ["project"]


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
    # AVP v0.1 §4: tools[] is the single bag of usable tools — local AND
    # MCP-surfaced. MCP-surfaced entries carry `avp.mcp_server_id`
    # extracted from the `mcp__<server>__<tool>` prefix.
    assert [t.name for t in desc.tools] == ["Bash", "Read", "Edit", "mcp__demo__search"]
    assert [t.mcp_server_id for t in desc.tools] == [None, None, None, "demo"]
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


def test_mcp_tool_decls_carry_catalog_description() -> None:
    """Decl fidelity (spec SHOULD): MCP-surfaced entries take `description`
    from the per-server catalog `get_mcp_status()` reports; built-ins stay
    name-only (the SDK exposes no catalog text for them), and an MCP handle
    absent from the server's catalog stays honest-null too."""
    events = asyncio.run(
        _drive_prelude(
            init=_init(tools=["Bash", "mcp__demo__search", "mcp__demo__unlisted"]),
        )
    )
    for ev_tools in (
        next(ev for ev in events if ev.type == "avp.agent_started").data.tools,
        next(ev for ev in events if ev.type == "avp.agent_described").data.descriptor.tools,
    ):
        by_name = {t.name: t for t in ev_tools}
        assert by_name["mcp__demo__search"].description == "Search the demo index."
        assert by_name["Bash"].description is None
        assert by_name["mcp__demo__unlisted"].description is None
        assert by_name["mcp__demo__unlisted"].mcp_server_id == "demo"


def test_agent_started_meta_carries_context_usage() -> None:
    """The `/context` breakdown rides on agent_started's `avp.meta` so the
    run's fixed input-token cost (system prompt / tool catalog / skills /
    memory) is attributable from the trajectory."""
    usage = {
        "totalTokens": 24381,
        "maxTokens": 1_000_000,
        "categories": [{"name": "System tools", "tokens": 12601, "color": "inactive"}],
        "skills": {"totalSkills": 2, "tokens": 120},
    }
    events: list[Event] = []
    state = _make_state(events)
    asyncio.run(
        emit_agent_started(
            state,
            prompt="ping",
            options=ClaudeAgentOptions(),
            init_data=_init().data,
            status=_status(),
            context_usage=usage,
        )
    )
    assert events[0].data.meta["claude_agent_sdk.context_usage"] == usage


def test_context_usage_meta_trims_and_survives_failure() -> None:
    """`context_usage_meta` keeps only attribution-relevant keys (gridRows
    and empty sections drop) and degrades to None when the control request
    fails (older CLI builds): the prelude must not depend on it."""

    class _Probe:
        async def get_context_usage(self):
            return {
                "totalTokens": 100,
                "maxTokens": 200_000,
                "categories": [{"name": "System prompt", "tokens": 100}],
                "systemTools": [],
                "gridRows": [["visual"]],
                "apiUsage": {"x": 1},
            }

    class _Broken:
        async def get_context_usage(self):
            raise RuntimeError("control request not supported")

    meta = asyncio.run(context_usage_meta(_Probe()))
    assert meta == {
        "totalTokens": 100,
        "maxTokens": 200_000,
        "categories": [{"name": "System prompt", "tokens": 100}],
    }
    assert asyncio.run(context_usage_meta(_Broken())) is None


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


def test_mcp_servers_include_non_connected_with_status() -> None:
    """AVP v0.1 §2.1: `mcp_servers[]` records every attempted dial with
    its terminal `status`. needs-auth / failed / disabled / pending
    servers stay on the wire so consumers see what was attempted; only
    their *tools* are excluded from `tools[]`."""
    events = asyncio.run(
        _drive_prelude(
            init=_init(),
            status=_status(connected_named="demo", extra_pending=True),
        )
    )
    started = next(ev for ev in events if ev.type == "avp.agent_started")
    described = next(ev for ev in events if ev.type == "avp.agent_described")
    assert [(s.id, s.status) for s in started.data.mcp_servers] == [
        ("demo", "connected"),
        ("claude.ai Gmail", "needs-auth"),
    ]
    assert [(s.id, s.status) for s in described.data.descriptor.mcp_servers] == [
        ("demo", "connected"),
        ("claude.ai Gmail", "needs-auth"),
    ]


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
                _result(result="done"),
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
                _result(),
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
                _result(),
            ]
        )
    )
    msgs = [ev for ev in events if ev.type == "avp.assistant_message"]
    assert len(msgs) == 1
    assert [b.type for b in msgs[0].data.content] == ["thinking", "text"]
    assert msgs[0].data.usage.input_tokens == 4
    assert msgs[0].data.usage.output_tokens == 6


def test_tool_result_boundary_opens_new_turn() -> None:
    """A parent-level `UserMessage(ToolResultBlock)` closes the open
    turn; the next AssistantMessage opens a fresh turn. Each turn's
    usage reflects its own inference's per-call totals (not a delta
    against an imaginary running session counter)."""
    events = asyncio.run(
        _drive(
            [
                _assistant(TextBlock(text="t1"), input_tokens=10, output_tokens=5),
                _user_tool_result(),
                _assistant(TextBlock(text="t2"), input_tokens=10, output_tokens=7),
                _result(),
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
                _result(),
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
                _result(result="done"),
            ]
        )
    )
    stopped = next(ev for ev in events if ev.type == "avp.agent_stopped")
    assert stopped.data.reason == "converged"
    assert stopped.data.output == "done"


def test_result_message_is_error_emits_error_reason() -> None:
    events = asyncio.run(_drive([_result(result=None, is_error=True, stop_reason="error")]))
    stopped = next(ev for ev in events if ev.type == "avp.agent_stopped")
    assert stopped.data.reason == "error"


def test_result_message_refusal_emits_refused_reason() -> None:
    events = asyncio.run(_drive([_result(result=None, is_error=False, stop_reason="refusal")]))
    stopped = next(ev for ev in events if ev.type == "avp.agent_stopped")
    assert stopped.data.reason == "refused"


def test_agent_stopped_is_idempotent() -> None:
    """ResultMessage handler fires once; a second call no-ops via state.stopped."""
    events = asyncio.run(_drive([_result(), _result()]))
    stops = [ev for ev in events if ev.type == "avp.agent_stopped"]
    assert len(stops) == 1


# ---------------------------------------------------------------------------
# Per-call usage isolation
# ---------------------------------------------------------------------------


def test_each_turn_reports_its_own_per_call_usage() -> None:
    """Each AVP `assistant_message` carries the per-API-call totals of
    its inference; turns are independent. A bigger-then-smaller pattern
    (e.g. compaction between turns) is fine — the second turn reports
    its own numbers, not deltas against the first."""
    events = asyncio.run(
        _drive(
            [
                _assistant(TextBlock(text="t1"), input_tokens=100, output_tokens=50),
                _user_tool_result(),
                _assistant(TextBlock(text="t2"), input_tokens=10, output_tokens=7),
                _result(),
            ]
        )
    )
    msgs = [ev for ev in events if ev.type == "avp.assistant_message"]
    assert len(msgs) == 2
    assert msgs[0].data.usage.input_tokens == 100
    assert msgs[0].data.usage.output_tokens == 50
    assert msgs[1].data.usage.input_tokens == 10
    assert msgs[1].data.usage.output_tokens == 7


# ---------------------------------------------------------------------------
# Tool bracketing (Stage 2 step 1)
# ---------------------------------------------------------------------------


def test_local_tool_use_emits_invoked_then_returned_paired_by_id() -> None:
    """A `ToolUseBlock` in an assistant turn followed by a
    `ToolResultBlock` in the next user message MUST produce a
    `tool_invoked` (parented to the assistant_message span) and a
    `tool_returned` (parented to the tool_invoked span). Both share
    `tool_call_id` and `tool_name`."""
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ToolUseBlock(id="toolu_42", name="Read", input={"path": "/x"}),
                    input_tokens=5,
                    output_tokens=3,
                ),
                _user_tool_result(tool_use_id="toolu_42", content="contents"),
                _result(),
            ]
        )
    )
    assistant_msgs = [ev for ev in events if ev.type == "avp.assistant_message"]
    invoked = [ev for ev in events if ev.type == "avp.tool_invoked"]
    returned = [ev for ev in events if ev.type == "avp.tool_returned"]
    assert len(invoked) == 1
    assert len(returned) == 1
    assert invoked[0].data.tool_call_id == "toolu_42"
    assert invoked[0].data.tool_name == "Read"
    assert invoked[0].data.tool_input == {"path": "/x"}
    assert invoked[0].data.tool_dispatch_target == "local"
    assert invoked[0].data.parent_span_id == assistant_msgs[0].data.span_id
    assert returned[0].data.tool_call_id == "toolu_42"
    assert returned[0].data.tool_name == "Read"
    assert returned[0].data.parent_span_id == invoked[0].data.span_id
    assert returned[0].data.tool_result.content == "contents"
    assert returned[0].data.tool_result.is_error is None


def test_mcp_prefixed_tool_dispatch_target_is_mcp_server() -> None:
    """Tool names matching `mcp__<server>__<tool>` MUST surface
    `dispatch_target="mcp_server"` per spec §4."""
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ToolUseBlock(id="t1", name="mcp__demo__search", input={"q": "x"}),
                    input_tokens=2,
                    output_tokens=2,
                ),
                _user_tool_result(tool_use_id="t1"),
                _result(),
            ]
        )
    )
    invoked = next(ev for ev in events if ev.type == "avp.tool_invoked")
    assert invoked.data.tool_dispatch_target == "mcp_server"


def test_tool_returned_carries_is_error_for_failed_results() -> None:
    """Tool failures (permission denials, runtime errors) ride
    `tool_result.is_error=True`; there is no `tool_failed` event."""
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ToolUseBlock(id="t1", name="Bash", input={"cmd": "ls"}),
                    input_tokens=2,
                    output_tokens=2,
                ),
                _user_tool_result(tool_use_id="t1", content="denied", is_error=True),
                _result(),
            ]
        )
    )
    returned = next(ev for ev in events if ev.type == "avp.tool_returned")
    assert returned.data.tool_result.is_error is True
    assert returned.data.tool_result.content == "denied"
    assert "avp.tool_failed" not in {ev.type for ev in events}


def test_unmatched_tool_result_is_dropped() -> None:
    """A `ToolResultBlock` whose `tool_use_id` has no preceding
    `tool_invoked` MUST NOT produce a `tool_returned`: emitting one
    would forge a parent span."""
    events = asyncio.run(
        _drive(
            [
                _assistant(TextBlock(text="hi"), input_tokens=1, output_tokens=1),
                _user_tool_result(tool_use_id="bogus"),
                _result(),
            ]
        )
    )
    assert not [ev for ev in events if ev.type == "avp.tool_returned"]


def test_server_tool_use_and_result_bracket_within_same_turn() -> None:
    """Server-side tools (web_search, code execution) complete inline:
    the SDK delivers `ServerToolUseBlock` and `ServerToolResultBlock`
    in the same assistant turn. Both `tool_invoked` and `tool_returned`
    MUST fire at turn close, and `dispatch_target` stays `local`
    (the agent never dispatches; the provider executes server-side)."""
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ServerToolUseBlock(id="srv_1", name="web_search", input={"q": "avp"}),
                    ServerToolResultBlock(
                        tool_use_id="srv_1",
                        content={"results": ["doc-1"]},
                    ),
                    input_tokens=3,
                    output_tokens=4,
                ),
                _result(),
            ]
        )
    )
    invoked = [ev for ev in events if ev.type == "avp.tool_invoked"]
    returned = [ev for ev in events if ev.type == "avp.tool_returned"]
    assert len(invoked) == 1
    assert len(returned) == 1
    assert invoked[0].data.tool_dispatch_target == "local"
    assert invoked[0].data.tool_name == "web_search"
    assert returned[0].data.parent_span_id == invoked[0].data.span_id
    # SDK ServerToolResultBlock carries content as a dict; the AVP
    # tool_result coerces it to a JSON-string via _normalize_tool_result_content.
    assert returned[0].data.tool_result.content == '{"results": ["doc-1"]}'


def test_tool_returned_carries_structured_content_from_user_message() -> None:
    """The SDK exposes a programmatic payload on `UserMessage.tool_use_result`
    (e.g. Glob → `{filenames, numFiles, durationMs, truncated}`) paired
    with the human-readable `content` string. When the user message has
    exactly one tool result, that dict MUST surface on
    `tool_returned.tool_result.structured_content` so consumers don't
    have to re-parse the text channel."""
    structured = {"filenames": ["a.md", "b.md"], "numFiles": 2}
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ToolUseBlock(id="t1", name="Glob", input={"pattern": "*.md"}),
                    input_tokens=2,
                    output_tokens=2,
                ),
                UserMessage(
                    content=[ToolResultBlock(tool_use_id="t1", content="a.md\nb.md")],
                    tool_use_result=structured,
                ),
                _result(),
            ]
        )
    )
    returned = next(ev for ev in events if ev.type == "avp.tool_returned")
    assert returned.data.tool_result.structured_content == structured
    assert returned.data.tool_result.content == "a.md\nb.md"


def test_tool_returned_wraps_non_dict_tool_use_result() -> None:
    """The SDK ships non-dict `tool_use_result` payloads (e.g.
    permission-denial errors arrive as a bare string). AVP's
    `structured_content` field is `dict[str, Any] | None`, so the
    translator wraps non-dict payloads as `{"result": val}` to keep the
    block validating instead of crashing the run."""
    err_str = (
        "Error: Claude requested permissions to use WebSearch, but you haven't granted it yet."
    )
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ToolUseBlock(id="t1", name="WebSearch", input={"query": "x"}),
                    input_tokens=2,
                    output_tokens=2,
                ),
                UserMessage(
                    content=[ToolResultBlock(tool_use_id="t1", content=err_str, is_error=True)],
                    tool_use_result=err_str,
                ),
                _result(),
            ]
        )
    )
    returned = next(ev for ev in events if ev.type == "avp.tool_returned")
    assert returned.data.tool_result.structured_content == {"result": err_str}
    assert returned.data.tool_result.content == err_str
    assert returned.data.tool_result.is_error is True


def test_tool_event_ordering_is_message_then_invoked_then_returned() -> None:
    """Per spec §8 #4, `tool_invoked` MUST precede `tool_returned`.
    `assistant_message` MUST precede `tool_invoked` since the model's
    decision to call the tool is part of the closing turn."""
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ToolUseBlock(id="t1", name="Read", input={"path": "/x"}),
                    input_tokens=2,
                    output_tokens=2,
                ),
                _user_tool_result(tool_use_id="t1"),
                _result(),
            ]
        )
    )
    tool_types = [
        ev.type
        for ev in events
        if ev.type in {"avp.assistant_message", "avp.tool_invoked", "avp.tool_returned"}
    ]
    assert tool_types == ["avp.assistant_message", "avp.tool_invoked", "avp.tool_returned"]


# ---------------------------------------------------------------------------
# Subagent bracketing (Stage 2 step 2)
# ---------------------------------------------------------------------------


def _task_started(
    tool_use_id: str = "toolu_task_1",
    task_id: str = "task_1",
    task_type: str | None = "general-purpose",
) -> TaskStartedMessage:
    return TaskStartedMessage(
        subtype="task_started",
        data={},
        task_id=task_id,
        description="explore the codebase",
        uuid="uuid-1",
        session_id="sess-1",
        tool_use_id=tool_use_id,
        task_type=task_type,
    )


def _task_notification(
    tool_use_id: str = "toolu_task_1",
    task_id: str = "task_1",
    status: str = "completed",
    summary: str = "done: found 7 markdown files",
    usage: dict[str, int] | None = None,
) -> TaskNotificationMessage:
    return TaskNotificationMessage(
        subtype="task_notification",
        data={},
        task_id=task_id,
        status=status,  # type: ignore[arg-type]
        output_file="/tmp/out",
        summary=summary,
        uuid="uuid-2",
        session_id="sess-1",
        tool_use_id=tool_use_id,
        usage=usage,  # type: ignore[arg-type]
    )


def _task_use_block(
    tool_id: str = "toolu_task_1",
    subagent_type: str = "general-purpose",
    name: str = "Agent",
) -> ToolUseBlock:
    """Build a dispatch ToolUseBlock. Default tool name is `Agent` to
    match the current SDK; the wire-event mapping is driven by the
    paired `TaskStartedMessage`, not the tool name."""
    return ToolUseBlock(
        id=tool_id,
        name=name,
        input={
            "description": "explore",
            "prompt": "find the markdown files",
            "subagent_type": subagent_type,
        },
    )


def test_task_dispatch_emits_tool_pair_with_subagent_overlay() -> None:
    """Per spec §5, subagent dispatches MUST emit both the tool pair
    (`tool_invoked` / `tool_returned`, so message-history reconstruction
    stays a direct read of `avp.content` + `tool_result`) AND the
    subagent overlay (`subagent_invoked` / `subagent_returned`,
    recording lifecycle + usage). Event order:
    `assistant_message → tool_invoked → subagent_invoked → subagent_returned → tool_returned`.
    The subagent frame nests under the tool-dispatch span."""
    events = asyncio.run(
        _drive(
            [
                _assistant(_task_use_block(), input_tokens=4, output_tokens=4),
                _task_started(),
                _task_notification(
                    summary="done",
                    usage={"total_tokens": 42, "tool_uses": 3, "duration_ms": 1234},
                ),
                _user_tool_result(tool_use_id="toolu_task_1", content="done"),
                _result(),
            ]
        )
    )
    types = [ev.type for ev in events]
    # All four lifecycle events present, in the spec-§5 order.
    assert types.count("avp.tool_invoked") == 1
    assert types.count("avp.subagent_invoked") == 1
    assert types.count("avp.subagent_returned") == 1
    assert types.count("avp.tool_returned") == 1
    bracketed = [
        t
        for t in types
        if t
        in {
            "avp.assistant_message",
            "avp.tool_invoked",
            "avp.subagent_invoked",
            "avp.subagent_returned",
            "avp.tool_returned",
        }
    ]
    assert bracketed == [
        "avp.assistant_message",
        "avp.tool_invoked",
        "avp.subagent_invoked",
        "avp.subagent_returned",
        "avp.tool_returned",
    ]
    tool_invoked = next(ev for ev in events if ev.type == "avp.tool_invoked")
    tool_returned = next(ev for ev in events if ev.type == "avp.tool_returned")
    invoked = next(ev for ev in events if ev.type == "avp.subagent_invoked")
    returned = next(ev for ev in events if ev.type == "avp.subagent_returned")
    # Tool pair preserves message-history integrity for the Task dispatch.
    assert tool_invoked.data.tool_call_id == "toolu_task_1"
    assert tool_invoked.data.tool_name == "Agent"
    assert tool_invoked.data.tool_dispatch_target == "local"
    assert tool_returned.data.tool_call_id == "toolu_task_1"
    assert tool_returned.data.tool_result.content == "done"
    # Subagent overlay carries the richer lifecycle.
    assert invoked.data.subagent_name == "general-purpose"
    assert invoked.data.subagent_invocation_id == "toolu_task_1"
    assert invoked.data.subagent_input["prompt"] == "find the markdown files"
    assert returned.data.subagent_result_text == "done"
    assert returned.data.subagent_reason == "converged"
    # Frame pairing: subagent_returned reuses subagent_invoked's span_id.
    assert returned.data.span_id == invoked.data.span_id
    # Spec §5: the subagent frame sits as a sibling of `tool_invoked`
    # under the enclosing turn span, not nested under the tool span.
    asst = next(ev for ev in events if ev.type == "avp.assistant_message")
    assert invoked.data.parent_span_id == asst.data.span_id
    assert returned.data.parent_span_id == asst.data.span_id
    assert tool_invoked.data.parent_span_id == asst.data.span_id
    # tool_returned closes the tool span.
    assert tool_returned.data.parent_span_id == tool_invoked.data.span_id


def test_task_failed_status_emits_returned_with_error_reason() -> None:
    """TaskNotification.status == 'failed' maps to `subagent_returned`
    with `reason = error` and the failure summary on `result.text`. The
    wrapping tool pair still fires (spec §5) so the model's
    message-history pairing stays intact; `tool_returned.is_error`
    reflects what the SDK reports on the synthetic tool result."""
    events = asyncio.run(
        _drive(
            [
                _assistant(_task_use_block(), input_tokens=2, output_tokens=2),
                _task_started(),
                _task_notification(status="failed", summary="auth error"),
                _user_tool_result(tool_use_id="toolu_task_1", content="auth error", is_error=True),
                _result(),
            ]
        )
    )
    types = {ev.type for ev in events}
    assert "avp.tool_invoked" in types
    assert "avp.tool_returned" in types
    subagent_returned = [ev for ev in events if ev.type == "avp.subagent_returned"]
    assert len(subagent_returned) == 1
    assert subagent_returned[0].data.subagent_reason == "error"
    assert subagent_returned[0].data.subagent_result_text == "auth error"
    returned = next(ev for ev in events if ev.type == "avp.tool_returned")
    assert returned.data.tool_result.is_error is True
    assert returned.data.tool_result.content == "auth error"


def test_task_stopped_status_emits_returned_with_interrupted_reason() -> None:
    """TaskNotification.status == 'stopped' maps to
    `subagent_returned.reason = "interrupted"`."""
    events = asyncio.run(
        _drive(
            [
                _assistant(_task_use_block(), input_tokens=2, output_tokens=2),
                _task_started(),
                _task_notification(status="stopped", summary="user cancelled"),
                _user_tool_result(tool_use_id="toolu_task_1", content="user cancelled"),
                _result(),
            ]
        )
    )
    returned = next(ev for ev in events if ev.type == "avp.subagent_returned")
    assert returned.data.subagent_reason == "interrupted"


def test_task_usage_rolls_up_onto_subagent_usage() -> None:
    """TaskUsage (`total_tokens`, `tool_uses`, `duration_ms`) rides on
    `subagent_returned.subagent_usage` as extras alongside the AVP
    canonical fields (which stay 0 since the SDK doesn't split
    input/output). This is the in-process-fallback rollup per spec §6."""
    events = asyncio.run(
        _drive(
            [
                _assistant(_task_use_block(), input_tokens=2, output_tokens=2),
                _task_started(),
                _task_notification(
                    summary="done",
                    usage={"total_tokens": 1500, "tool_uses": 5, "duration_ms": 7000},
                ),
                _user_tool_result(tool_use_id="toolu_task_1", content="done"),
                _result(),
            ]
        )
    )
    returned = next(ev for ev in events if ev.type == "avp.subagent_returned")
    usage = returned.data.subagent_usage
    assert usage is not None
    assert usage.cost_usd == 0.0
    assert usage.tokens_input == 0
    assert usage.tokens_output == 0
    assert usage.turns == 0
    dumped = usage.model_dump(by_alias=True, exclude_none=True)
    assert dumped["total_tokens"] == 1500
    assert dumped["tool_uses"] == 5
    assert dumped["duration_ms"] == 7000


def test_task_progress_messages_are_dropped() -> None:
    """`TaskProgressMessage` is informational only; it MUST NOT emit
    any AVP event of its own."""
    events = asyncio.run(
        _drive(
            [
                _assistant(_task_use_block(), input_tokens=2, output_tokens=2),
                _task_started(),
                TaskProgressMessage(
                    subtype="task_progress",
                    data={},
                    task_id="task_1",
                    description="in flight",
                    usage={"total_tokens": 50, "tool_uses": 1, "duration_ms": 100},  # type: ignore[arg-type]
                    uuid="p",
                    session_id="sess-1",
                    tool_use_id="toolu_task_1",
                ),
                _task_notification(summary="done"),
                _user_tool_result(tool_use_id="toolu_task_1", content="done"),
                _result(),
            ]
        )
    )
    # Progress contributes no events; we still get exactly one invoked/returned pair.
    assert len([ev for ev in events if ev.type == "avp.subagent_invoked"]) == 1
    assert len([ev for ev in events if ev.type == "avp.subagent_returned"]) == 1


def test_parallel_subagent_dispatch_merges_into_one_assistant_message() -> None:
    """One Anthropic API response with multiple content blocks (one
    thinking block + two parallel Task dispatches) is fanned out by the
    CLI as multiple `AssistantMessage` Python objects sharing one
    `message_id`, with `TaskStartedMessage`s interleaved between
    chunks. The agent MUST coalesce them into exactly ONE
    `assistant_message` AVP event carrying all three blocks; the four
    lifecycle events per dispatch (tool_invoked → subagent_invoked →
    subagent_returned → tool_returned, spec §5) MUST land after the
    merged `assistant_message`. Each subagent frame nests under its own
    tool-dispatch span. Regression for the pre-fix bug where
    TaskStartedMessage forced a turn close mid-inference, splitting
    the parallel dispatches across a phantom second turn that the
    empty-output gate then dropped, leaving the second dispatch's
    `tool_use` block off the wire."""
    ny_block = _task_use_block(tool_id="toolu_NY", subagent_type="general-purpose")
    zh_block = _task_use_block(tool_id="toolu_ZH", subagent_type="general-purpose")
    events = asyncio.run(
        _drive(
            [
                _assistant(
                    ThinkingBlock(thinking="ponder", signature="sig"),
                    message_id="msg_PARALLEL",
                    input_tokens=6,
                    output_tokens=8,
                ),
                _assistant(
                    ny_block,
                    message_id="msg_PARALLEL",
                    input_tokens=6,
                    output_tokens=8,
                ),
                _task_started(tool_use_id="toolu_NY", task_id="task_NY"),
                _assistant(
                    zh_block,
                    message_id="msg_PARALLEL",
                    input_tokens=6,
                    output_tokens=8,
                ),
                _task_started(tool_use_id="toolu_ZH", task_id="task_ZH"),
                # Notifications can arrive before the closing UserMessage;
                # they defer until subagent_invoked lands.
                _task_notification(tool_use_id="toolu_NY", task_id="task_NY", summary="NY done"),
                _user_tool_result(tool_use_id="toolu_NY", content="NY done"),
                _task_notification(tool_use_id="toolu_ZH", task_id="task_ZH", summary="ZH done"),
                _user_tool_result(tool_use_id="toolu_ZH", content="ZH done"),
                _result(),
            ]
        )
    )
    asst_msgs = [ev for ev in events if ev.type == "avp.assistant_message"]
    assert len(asst_msgs) == 1
    asst = asst_msgs[0]
    assert [b.type for b in asst.data.content] == ["thinking", "tool_use", "tool_use"]
    assert [b.id for b in asst.data.content if b.type == "tool_use"] == ["toolu_NY", "toolu_ZH"]
    # Per-API-call usage: every chunk reports the same totals; the
    # merged turn carries those totals once, not summed.
    assert asst.data.usage.input_tokens == 6
    assert asst.data.usage.output_tokens == 8

    tool_invoked = [ev for ev in events if ev.type == "avp.tool_invoked"]
    tool_returned = [ev for ev in events if ev.type == "avp.tool_returned"]
    invoked = [ev for ev in events if ev.type == "avp.subagent_invoked"]
    returned = [ev for ev in events if ev.type == "avp.subagent_returned"]
    assert [ev.data.tool_call_id for ev in tool_invoked] == ["toolu_NY", "toolu_ZH"]
    assert sorted(ev.data.tool_call_id for ev in tool_returned) == ["toolu_NY", "toolu_ZH"]
    assert [ev.data.subagent_invocation_id for ev in invoked] == ["toolu_NY", "toolu_ZH"]
    assert sorted(ev.data.subagent_invocation_id for ev in returned) == ["toolu_NY", "toolu_ZH"]
    # Both tool_invoked and subagent_invoked parent under the turn span
    # (sibling pair per spec §5, not nested).
    for ti in tool_invoked:
        assert ti.data.parent_span_id == asst.data.span_id
    for inv in invoked:
        assert inv.data.parent_span_id == asst.data.span_id

    # Ordering: assistant_message strictly precedes every tool_invoked /
    # subagent_invoked. Per dispatch, tool_invoked precedes subagent_invoked.
    types = [ev.type for ev in events]
    asst_idx = types.index("avp.assistant_message")
    for i, t in enumerate(types):
        if t in {"avp.tool_invoked", "avp.subagent_invoked"}:
            assert i > asst_idx


def test_task_without_lifecycle_emits_tool_pair_only() -> None:
    """If the SDK doesn't surface TaskStartedMessage (e.g. older SDK,
    edge case), a `ToolUseBlock(name="Agent")` still produces the
    regular `tool_invoked` / `tool_returned` pair (per spec §5, that
    pair is always emitted for Task dispatches now); the subagent
    overlay simply doesn't fire without the lifecycle messages."""
    events = asyncio.run(
        _drive(
            [
                _assistant(_task_use_block(), input_tokens=2, output_tokens=2),
                _user_tool_result(tool_use_id="toolu_task_1", content="done"),
                _result(),
            ]
        )
    )
    types = {ev.type for ev in events}
    assert "avp.tool_invoked" in types
    assert "avp.tool_returned" in types
    assert "avp.subagent_invoked" not in types
    assert "avp.subagent_returned" not in types
