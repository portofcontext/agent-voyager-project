"""Stateless AVP event emitters and SDK message dispatcher.

Low-level emitters (`emit_prelude`, `emit_agent_stopped`) take a
`RunState` and emit exactly the events their name implies, mutating
state as needed. `handle_message` is the single entry point for the
SDK stream: it dispatches each `claude_agent_sdk` message to the right
emitter and is reusable across all client wrappers.

Stage 1: prelude, merged `assistant_message` (content + per-turn usage
+ computed cost), `agent_stopped`, merge gate.
Stage 2: `tool_invoked` / `tool_returned`, `subagent_invoked` /
`subagent_returned`.
"""

from __future__ import annotations

import time
from typing import Any

from claude_agent_sdk.types import ClaudeAgentOptions, McpStatusResponse

from avp._envelope import ZERO_SPAN_ID, new_span_id
from avp.content import AVPContentBlock
from avp.content import TextBlock as AVPTextBlock
from avp.content import ThinkingBlock as AVPThinkingBlock
from avp.content import ToolUseBlock as AVPToolUseBlock
from avp.pricing import compute_cost
from avp.trajectory import (
    AgentDescribedData,
    AgentDescribedEvent,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    AssistantMessageData,
    AssistantMessageEvent,
    RunRequestedData,
    RunRequestedEvent,
    StopReason,
    Usage,
)
from avp_claude_agent_sdk._runstate import RunState
from avp_claude_agent_sdk._translator import (
    descriptor_full,
    mcp_servers_connected,
    request_model_from_init,
    resolve_system_prompt,
    skills_from_init,
    subagents_from_init,
    tools_from_init,
)

_PROVIDER_NAME = "anthropic"

# ---------------------------------------------------------------------------
# Prelude
# ---------------------------------------------------------------------------
#
# Per spec §2.1, the prelude carries two semantically distinct snapshots:
#
#   - `agent_described` is the agent's full self-published capability
#     surface ("what is currently available"). For claude-agent-sdk this
#     is discovered via a transient probe session in `connect()`: boot,
#     drain the first `SystemMessage(subtype="init")`, disconnect.
#   - `agent_started` is the merged-state view ("what the run will
#     actually use"), with Commission filters applied. For now (no
#     Commission path), it carries the same surface as the descriptor;
#     Stage 3 will introduce Commission merging that filters /
#     supplements this view without changing the wire shape.


async def emit_run_requested(state: RunState) -> None:
    """First event of the trajectory. Anchors the run.

    No Commission on the `AVPClaudeSDKClient` path (Stage 3 adds the
    Commission-driven `run_avp_agent` entry point that fills
    `avp.commission` / `avp.supervisor.*`).
    """
    await state.sink(
        RunRequestedEvent(
            subject=state.run_id,
            data=RunRequestedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
            ),
        )
    )


async def emit_agent_described(
    state: RunState,
    options: ClaudeAgentOptions,
    *,
    prompt: str | None,
    init_data: dict[str, Any] | None,
    status: McpStatusResponse,
) -> None:
    """Emit `agent_described` with the agent's full pre-Commission
    capability surface.

    `init_data` comes from a probe session's `SystemMessage(init)`;
    `status` from the probe's `get_mcp_status()`. Together they describe
    the full agent capability surface before any Commission filter.
    When `init_data` is `None` (probe unavailable / failed), the
    descriptor carries identity + default_model only -- the prelude
    stays spec-conformant but `tools` / `subagents` / `skills` are absent.
    """
    await state.sink(
        AgentDescribedEvent(
            subject=state.run_id,
            data=AgentDescribedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
                descriptor=descriptor_full(options, init_data, status, prompt=prompt),
            ),
        )
    )


async def emit_agent_started(
    state: RunState,
    *,
    prompt: str | None,
    options: ClaudeAgentOptions,
    init_data: dict[str, Any] | None,
    status: McpStatusResponse,
) -> None:
    """Emit `agent_started`: merged-state snapshot for the run.

    Without a Commission this is the same surface as `agent_described`
    (no merge to do). Stage 3 will add Commission filtering here
    (`enabled_builtin_tools`, `enabled_builtin_mcp_servers`, merging in
    Commission-managed refs); the wire shape doesn't change.

    Sets `state.agent_span_id` for subsequent turn / tool events to
    parent under.
    """
    agent_span_id = new_span_id()
    state.agent_span_id = agent_span_id
    await state.sink(
        AgentStartedEvent(
            subject=state.run_id,
            data=AgentStartedData(
                trace_id=state.trace_id,
                span_id=agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                provider_name=_PROVIDER_NAME,
                operation_name="invoke_agent",
                request_model=(
                    request_model_from_init(init_data, options)
                    if init_data
                    else options.model
                ),
                prompt=prompt,
                system_prompt=resolve_system_prompt(options.system_prompt),
                tools=tools_from_init(init_data) if init_data else None,
                mcp_servers=mcp_servers_connected(status),
                skills=skills_from_init(init_data) if init_data else None,
                subagents=subagents_from_init(init_data) if init_data else None,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Terminal
# ---------------------------------------------------------------------------


async def emit_agent_stopped(
    state: RunState,
    reason: StopReason,
    *,
    output: Any = None,
) -> None:
    """Emit agent_stopped. Always the last event on the wire. Idempotent
    via `state.stopped`: subsequent calls no-op so disconnect() fallback
    and the ResultMessage handler don't double-fire."""
    if state.stopped:
        return
    state.stopped = True
    await state.sink(
        AgentStoppedEvent(
            subject=state.run_id,
            data=AgentStoppedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=state.agent_span_id or ZERO_SPAN_ID,
                reason=reason,
                output=output,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Per-turn open / close
# ---------------------------------------------------------------------------


def _open_turn(state: RunState) -> None:
    """Allocate a new turn span, reset the accumulator, record start time."""
    state.step += 1
    state.current_turn_span_id = new_span_id()
    state.turn_started_at = time.monotonic()
    state.turn_content = []
    state.turn_usage_delta = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    state.turn_response_model = None
    state.turn_stop_reason = None


async def _close_turn(state: RunState) -> None:
    """Drain the accumulator into one assistant_message. Empty-output gate:
    skip the emit when `delta_output == 0` (no real model inference happened).

    Per spec §3.1: every model inference MUST be bracketed by an
    assistant_message; a turn with no output tokens isn't an inference.
    """
    if state.current_turn_span_id is None:
        return

    delta = state.turn_usage_delta
    if delta["output"] <= 0:
        # Reset and bail without emitting.
        state.current_turn_span_id = None
        return

    duration_ms = (
        int((time.monotonic() - state.turn_started_at) * 1000)
        if state.turn_started_at is not None
        else 0
    )
    usage = Usage(
        input_tokens=delta["input"],
        output_tokens=delta["output"],
        cache_read_input_tokens=delta["cache_read"] or None,
        cache_creation_input_tokens=delta["cache_creation"] or None,
    )
    cost_usd, cost_source = compute_cost(
        state.turn_response_model or "",
        input_tokens=delta["input"],
        output_tokens=delta["output"],
        cache_read=delta["cache_read"],
        cache_write=delta["cache_creation"],
        prices=state.prices,
    )
    await state.sink(
        AssistantMessageEvent(
            subject=state.run_id,
            data=AssistantMessageData(
                trace_id=state.trace_id,
                span_id=state.current_turn_span_id,
                parent_span_id=state.agent_span_id,
                step=state.step,
                duration_ms=duration_ms,
                content=list(state.turn_content),
                provider_name=_PROVIDER_NAME,
                request_model=state.turn_response_model,
                response_model=state.turn_response_model,
                response_finish_reasons=(
                    [state.turn_stop_reason] if state.turn_stop_reason else None
                ),
                usage=usage,
                cost_usd=cost_usd,
                cost_source=cost_source,
            ),
        )
    )
    state.current_turn_span_id = None


# ---------------------------------------------------------------------------
# Content + usage translation
# ---------------------------------------------------------------------------


def _translate_blocks(blocks: list[Any]) -> list[AVPContentBlock]:
    """SDK content blocks → AVP content blocks. Drops unknown subtypes
    (honest-silent beats fabricated). Server tool blocks land in Stage 2."""
    out: list[AVPContentBlock] = []
    for block in blocks or []:
        kind = type(block).__name__
        if kind == "TextBlock":
            out.append(AVPTextBlock(text=block.text))
        elif kind == "ThinkingBlock":
            out.append(
                AVPThinkingBlock(
                    thinking=block.thinking,
                    signature=getattr(block, "signature", None),
                )
            )
        elif kind == "ToolUseBlock":
            out.append(AVPToolUseBlock(id=block.id, name=block.name, input=block.input))
    return out


def _update_usage(state: RunState, usage: dict[str, Any] | None) -> None:
    """Fold an `AssistantMessage.usage` into the turn delta + bump prev_cum.

    SDK usage is cumulative across the session. Compute delta against
    `prev_cum`; rebase silently when the SDK's count drops below it
    (compaction / subagent dispatch reset, per spec §3.3).
    """
    if not usage:
        return
    cum = {
        "input": int(usage.get("input_tokens") or 0),
        "output": int(usage.get("output_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_creation": int(usage.get("cache_creation_input_tokens") or 0),
    }
    for key, cur in cum.items():
        prev = state.prev_cum[key]
        delta = cur - prev if cur >= prev else cur  # silent rebase
        state.turn_usage_delta[key] += max(0, delta)
        state.prev_cum[key] = cur


# ---------------------------------------------------------------------------
# Per-message handlers
# ---------------------------------------------------------------------------


async def _on_assistant(state: RunState, message: Any) -> None:
    # Merge gate: a new turn opens only when no turn is open, OR a tool
    # result arrived since the last AssistantMessage. Consecutive
    # AssistantMessages within one LLM call (thinking + text) APPEND
    # into the open turn.
    if state.current_turn_span_id is None:
        _open_turn(state)
        state.tool_result_arrived = False

    state.turn_content.extend(_translate_blocks(message.content))
    if state.turn_response_model is None:
        state.turn_response_model = getattr(message, "model", None)
    stop_reason = getattr(message, "stop_reason", None)
    if stop_reason:
        state.turn_stop_reason = stop_reason
    _update_usage(state, getattr(message, "usage", None))


async def _on_user(state: RunState, message: Any) -> None:
    content = getattr(message, "content", None) or []
    has_tool_result = any(type(b).__name__ == "ToolResultBlock" for b in content)
    if not has_tool_result:
        return
    # Close the in-flight turn (emit its assistant_message) before the
    # tool result is recorded. Stage 2 will emit tool_returned events
    # here as well, parented to the saved tool span_ids.
    if state.current_turn_span_id is not None:
        await _close_turn(state)
    state.tool_result_arrived = True


async def _on_result(state: RunState, message: Any) -> None:
    # Drain any pending turn before stopping.
    if state.current_turn_span_id is not None:
        await _close_turn(state)
    if getattr(message, "is_error", False):
        reason = StopReason.error
    elif getattr(message, "stop_reason", None) == "refusal":
        reason = StopReason.refused
    else:
        reason = StopReason.converged
    await emit_agent_stopped(state, reason, output=getattr(message, "result", None))


# ---------------------------------------------------------------------------
# Public dispatch entry point
# ---------------------------------------------------------------------------


async def handle_message(state: RunState, message: Any) -> None:
    """Dispatch one SDK message to the appropriate AVP emitter. Mutates state.

    Class-name dispatch (`type(message).__name__`) keeps this decoupled
    from SDK class identity / hierarchy changes.
    """
    msg_type = type(message).__name__
    if msg_type == "AssistantMessage":
        await _on_assistant(state, message)
    elif msg_type == "UserMessage":
        await _on_user(state, message)
    elif msg_type == "ResultMessage":
        await _on_result(state, message)
    # SystemMessage, RateLimitEvent, StreamEvent: Stage 2+
