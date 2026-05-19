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

import json
import time
from typing import Any, Literal

from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    ContentBlock,
    McpStatusResponse,
    Message,
    ResultMessage,
    ServerToolResultBlock,
    ServerToolUseBlock,
    TaskNotificationMessage,
    TaskStartedMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from avp._envelope import ZERO_SPAN_ID, new_span_id
from avp.content import AVPContentBlock
from avp.content import ServerToolResultBlock as AVPServerToolResultBlock
from avp.content import ServerToolUseBlock as AVPServerToolUseBlock
from avp.content import TextBlock as AVPTextBlock
from avp.content import ThinkingBlock as AVPThinkingBlock
from avp.content import ToolResultBlock as AVPToolResultBlock
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
    SubagentFailedData,
    SubagentFailedEvent,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentReturnedData,
    SubagentReturnedEvent,
    SubagentUsage,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    Usage,
)
from avp_claude_agent_sdk._runstate import RunState, TaskInfo, ToolCallInfo
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
                    request_model_from_init(init_data, options) if init_data else options.model
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
    # The remembered dispatch turn only belonged to the previous parent
    # turn's parallel batch; clear it so subsequent batches don't reuse
    # a stale span.
    state.last_dispatch_turn_span_id = None


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
    turn_span_id = state.current_turn_span_id
    await state.sink(
        AssistantMessageEvent(
            subject=state.run_id,
            data=AssistantMessageData(
                trace_id=state.trace_id,
                span_id=turn_span_id,
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
    # Walk the just-emitted content and bracket every tool use:
    # `tool_invoked` for both local/MCP `ToolUseBlock`s (paired with the
    # next `UserMessage(ToolResultBlock)`) and `ServerToolUseBlock`s,
    # which are followed inline by their `ServerToolResultBlock` and so
    # close out within the same turn.
    for block in state.turn_content:
        if isinstance(block, AVPToolUseBlock):
            # Subagent dispatches (id present in `state.task_info`) are
            # bracketed by the lifecycle handlers — `_on_task_started`
            # emits `subagent_invoked`, `_on_task_notification` emits
            # `subagent_returned` / `subagent_failed` — so the dispatch
            # ToolUseBlock stays in the assistant_message content for
            # fidelity but produces no `tool_invoked` here.
            if block.id in state.task_info:
                continue
            await _emit_tool_invoked(
                state,
                parent_span_id=turn_span_id,
                tool_call_id=block.id,
                tool_name=block.name,
                tool_input=block.input,
                dispatch_target=_dispatch_target(block.name),
            )
        elif isinstance(block, AVPServerToolUseBlock):
            await _emit_tool_invoked(
                state,
                parent_span_id=turn_span_id,
                tool_call_id=block.id,
                tool_name=block.name,
                tool_input=block.input,
                dispatch_target="local",
            )
        elif isinstance(block, AVPServerToolResultBlock):
            await _emit_tool_returned(
                state,
                tool_use_id=block.tool_use_id,
                result=AVPToolResultBlock(
                    tool_use_id=block.tool_use_id,
                    content=_normalize_tool_result_content(block.content),
                    is_error=block.is_error,
                ),
            )
    state.current_turn_span_id = None


# ---------------------------------------------------------------------------
# Content + usage translation
# ---------------------------------------------------------------------------


def _translate_blocks(blocks: list[ContentBlock]) -> list[AVPContentBlock]:
    """SDK content blocks → AVP content blocks. Drops unknown subtypes
    (honest-silent beats fabricated). `ToolResultBlock` is handled in
    `_on_user` (becomes a `tool_returned` event, not inline content).

    The SDK's `ServerToolResultBlock` doesn't carry `name` (only its
    paired `ServerToolUseBlock` does), so a single in-order pass tracks
    the most recent server-tool name per `tool_use_id` and back-fills it
    on the AVP result block.
    """
    out: list[AVPContentBlock] = []
    server_tool_names: dict[str, str] = {}
    for block in blocks or []:
        if isinstance(block, TextBlock):
            out.append(AVPTextBlock(text=block.text))
        elif isinstance(block, ThinkingBlock):
            out.append(AVPThinkingBlock(thinking=block.thinking, signature=block.signature))
        elif isinstance(block, ToolUseBlock):
            out.append(AVPToolUseBlock(id=block.id, name=block.name, input=block.input))
        elif isinstance(block, ServerToolUseBlock):
            server_tool_names[block.id] = block.name
            out.append(AVPServerToolUseBlock(id=block.id, name=block.name, input=block.input))
        elif isinstance(block, ServerToolResultBlock):
            out.append(
                AVPServerToolResultBlock(
                    tool_use_id=block.tool_use_id,
                    name=server_tool_names.get(block.tool_use_id, ""),
                    content=block.content,
                )
            )
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
# Tool bracketing
# ---------------------------------------------------------------------------


def _dispatch_target(tool_name: str) -> Literal["mcp_server", "local"]:
    """Pick the wire discriminator for `tool_invoked`. Claude Agent SDK
    namespaces MCP tools as `mcp__<server>__<tool>`; everything else is
    a CLI built-in or local hook."""
    return "mcp_server" if tool_name.startswith("mcp__") else "local"


def _normalize_tool_result_content(content: Any) -> str | list[Any]:
    """Coerce arbitrary tool-result payloads into AVP `ToolResultBlock.content`.

    Anthropic permits nested text/image/document blocks but the Claude
    Agent SDK surfaces them as opaque dicts; full block translation
    lands later. For now: pass strings through, stringify `None` to ""
    so the AVP block validates, and JSON-encode any other shape so the
    payload survives the wire intact (lossily, but observably)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, default=str)
    except (TypeError, ValueError):
        return str(content)


async def _emit_tool_invoked(
    state: RunState,
    *,
    parent_span_id: str,
    tool_call_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    dispatch_target: Literal["mcp_server", "local"],
) -> None:
    """Emit `tool_invoked` and record the span for later pairing.

    Parent is the open turn span; consumers tree `tool_returned` under
    this span via `state.tool_spans[tool_call_id]`.
    """
    span_id = new_span_id()
    state.tool_spans[tool_call_id] = ToolCallInfo(
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=tool_name,
        step=state.step,
        started_at=time.monotonic(),
    )
    await state.sink(
        ToolInvokedEvent(
            subject=state.run_id,
            data=ToolInvokedData(
                trace_id=state.trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                step=state.step,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_dispatch_target=dispatch_target,
            ),
        )
    )


async def _emit_tool_returned(
    state: RunState,
    *,
    tool_use_id: str,
    result: AVPToolResultBlock,
) -> None:
    """Emit `tool_returned`, paired against `state.tool_spans`.

    Unmatched ids (no preceding `tool_invoked`) drop silently: emitting
    a `tool_returned` without a pair would forge a span hierarchy.
    """
    info = state.tool_spans.pop(tool_use_id, None)
    if info is None:
        return
    duration_ms = max(0, int((time.monotonic() - info.started_at) * 1000))
    await state.sink(
        ToolReturnedEvent(
            subject=state.run_id,
            data=ToolReturnedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=info.span_id,
                step=info.step,
                tool_call_id=tool_use_id,
                tool_name=info.name,
                duration_ms=duration_ms,
                tool_result=result,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Subagent bracketing (Task tool dispatch)
# ---------------------------------------------------------------------------


_TASK_STATUS_TO_REASON: dict[str, StopReason] = {
    "completed": StopReason.converged,
    "stopped": StopReason.interrupted,
}


def _subagent_name(block: AVPToolUseBlock, task: TaskInfo | None) -> str:
    """Pick the subagent's declared name.

    Primary source is `TaskStartedMessage.task_type` (the SDK's
    authoritative lifecycle signal, surfaced via `TaskInfo`). Falls
    back to the dispatch tool's `input.subagent_type` (Claude Code's
    `Agent` / `Task` tool shape is `{subagent_type, description,
    prompt}`), then to `"Task"` so the event still validates if a
    future SDK version reshapes both."""
    if task is not None and task.task_type:
        return task.task_type
    subagent_type = block.input.get("subagent_type")
    if isinstance(subagent_type, str) and subagent_type:
        return subagent_type
    return "Task"


def _task_usage_to_subagent_usage(usage: dict[str, Any] | None) -> SubagentUsage | None:
    """Project a `TaskUsage` TypedDict onto AVP `SubagentUsage`.

    `TaskUsage` carries `{total_tokens, tool_uses, duration_ms}` without
    an input/output split or cost. Required AVP fields stay at 0 (honest
    sentinel — we don't know); the raw triple rides along as extras
    (allowed by `SubagentUsage.model_config = _OPEN`) so consumers that
    care about the SDK's actual shape can read them.
    """
    if not usage:
        return None
    return SubagentUsage(
        cost_usd=0.0,
        tokens_input=0,
        tokens_output=0,
        turns=0,
        total_tokens=int(usage.get("total_tokens") or 0),
        tool_uses=int(usage.get("tool_uses") or 0),
        duration_ms=int(usage.get("duration_ms") or 0),
    )


async def _emit_subagent_invoked(
    state: RunState,
    *,
    parent_span_id: str,
    block: AVPToolUseBlock,
) -> None:
    """Emit `subagent_invoked` for a Task ToolUseBlock and record the
    span for later pairing. The event's `span_id` IS the subagent's
    frame span (spec §6); descendants of the subagent (if the SDK ever
    surfaces them) would parent under it."""
    span_id = new_span_id()
    name = _subagent_name(block, state.task_info.get(block.id))
    state.subagent_spans[block.id] = ToolCallInfo(
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        step=state.step,
        started_at=time.monotonic(),
    )
    await state.sink(
        SubagentInvokedEvent(
            subject=state.run_id,
            data=SubagentInvokedData(
                trace_id=state.trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                step=state.step,
                subagent_name=name,
                subagent_invocation_id=block.id,
                subagent_input=block.input,
            ),
        )
    )


async def _emit_subagent_returned_or_failed(
    state: RunState,
    *,
    tool_use_id: str,
    result_text: str,
) -> None:
    """Close the subagent frame. Driven by `TaskNotificationMessage` via
    `_on_task_notification`: `status == "failed"` emits `subagent_failed`,
    `completed` / `stopped` emit `subagent_returned` with the matching
    `StopReason`. `state.task_info[tool_use_id]` is left in place so the
    synthetic `UserMessage(ToolResultBlock)` that follows can still be
    recognized and dropped in `_on_user`."""
    info = state.subagent_spans.pop(tool_use_id, None)
    if info is None:
        return
    task = state.task_info.get(tool_use_id)
    duration_ms = max(0, int((time.monotonic() - info.started_at) * 1000))
    status = task.status if task else None
    if status == "failed":
        await state.sink(
            SubagentFailedEvent(
                subject=state.run_id,
                data=SubagentFailedData(
                    trace_id=state.trace_id,
                    span_id=new_span_id(),
                    parent_span_id=info.span_id,
                    step=info.step,
                    subagent_name=info.name,
                    subagent_invocation_id=tool_use_id,
                    duration_ms=duration_ms,
                    subagent_error=(task.summary if task and task.summary else result_text),
                ),
            )
        )
        return
    reason = _TASK_STATUS_TO_REASON.get(status or "", StopReason.converged)
    summary_text = task.summary if task and task.summary else result_text
    await state.sink(
        SubagentReturnedEvent(
            subject=state.run_id,
            data=SubagentReturnedData(
                trace_id=state.trace_id,
                # span_id matches subagent_invoked: same frame, closed.
                span_id=info.span_id,
                # Parent the close under the frame's own parent (the
                # turn span), not the frame itself.
                parent_span_id=info.parent_span_id,
                step=info.step,
                subagent_name=info.name,
                subagent_invocation_id=tool_use_id,
                duration_ms=duration_ms,
                subagent_result_text=summary_text,
                subagent_reason=reason,
                subagent_usage=_task_usage_to_subagent_usage(task.usage if task else None),
            ),
        )
    )


# ---------------------------------------------------------------------------
# Per-message handlers
# ---------------------------------------------------------------------------


async def _on_assistant(state: RunState, message: AssistantMessage) -> None:
    # Subagent-interior AssistantMessages (`parent_tool_use_id` set) are
    # part of the in-process subagent fallback per spec §5.6: the parent
    # treats the child as a black box and summarizes its spend on
    # `subagent_returned` via `SubagentUsage` instead of leaking the
    # child's turns into the parent's flow. Skip them entirely — no
    # parent-turn merge and no parent-usage update.
    if message.parent_tool_use_id is not None:
        return
    # Merge gate: a new turn opens only when no turn is open, OR a tool
    # result arrived since the last AssistantMessage. Consecutive
    # AssistantMessages within one LLM call (thinking + text) APPEND
    # into the open turn.
    if state.current_turn_span_id is None:
        _open_turn(state)
        state.tool_result_arrived = False

    state.turn_content.extend(_translate_blocks(message.content))
    if state.turn_response_model is None:
        state.turn_response_model = message.model
    if message.stop_reason:
        state.turn_stop_reason = message.stop_reason
    _update_usage(state, message.usage)


async def _on_user(state: RunState, message: UserMessage) -> None:
    # Subagent-interior UserMessages (`parent_tool_use_id` set) carry
    # the subagent's prompt or its own tool results; skip them under the
    # in-process subagent fallback (spec §5.6).
    if message.parent_tool_use_id is not None:
        return
    # UserMessage.content is `str | list[ContentBlock]`. A plain string
    # carries no tool result, so only the list form is inspected.
    content = message.content if isinstance(message.content, list) else []
    tool_results = [b for b in content if isinstance(b, ToolResultBlock)]
    if not tool_results:
        return
    # Close the in-flight turn (emit its assistant_message + bracketing
    # tool_invoked events for blocks this turn produced) before the
    # tool result events fire. For subagent-only dispatch batches the
    # parent turn was already closed by `_on_task_started`, so this is
    # a no-op there.
    if state.current_turn_span_id is not None:
        await _close_turn(state)
    # `UserMessage.tool_use_result` is the SDK's structured-payload
    # channel (e.g. Glob → `{filenames, numFiles, durationMs, truncated}`)
    # paired with the human-readable `ToolResultBlock.content` string.
    # It lives at the message level, not per-block, so attribution is
    # only unambiguous when there's exactly one result; multi-result
    # messages drop the structured channel to avoid mis-attribution.
    # SDK ships non-dict payloads too (e.g. permission-denial errors come
    # through as a string); wrap those as `{"result": val}` so the
    # dict-typed AVP field still validates.
    structured: dict[str, Any] | None
    if len(tool_results) == 1 and message.tool_use_result is not None:
        raw = message.tool_use_result
        structured = raw if isinstance(raw, dict) else {"result": raw}
    else:
        structured = None
    for block in tool_results:
        # Synthetic ToolResultBlock for a subagent dispatch: its
        # `subagent_returned` / `subagent_failed` already fired from the
        # paired `TaskNotificationMessage` (lifecycle-driven), so drop
        # it from the wire instead of emitting `tool_returned`.
        if block.tool_use_id in state.task_info:
            continue
        await _emit_tool_returned(
            state,
            tool_use_id=block.tool_use_id,
            result=AVPToolResultBlock(
                tool_use_id=block.tool_use_id,
                content=_normalize_tool_result_content(block.content),
                structured_content=structured,
                is_error=block.is_error,
            ),
        )
    state.tool_result_arrived = True


async def _on_result(state: RunState, message: ResultMessage) -> None:
    # Drain any pending turn before stopping.
    if state.current_turn_span_id is not None:
        await _close_turn(state)
    if message.is_error:
        reason = StopReason.error
    elif message.stop_reason == "refusal":
        reason = StopReason.refused
    else:
        reason = StopReason.converged
    await emit_agent_stopped(state, reason, output=message.result)


async def _on_task_started(state: RunState, message: TaskStartedMessage) -> None:
    """Drive `subagent_invoked` from the SDK lifecycle.

    Records the `TaskInfo` (so `_close_turn` and `_on_user` recognize
    this tool_use_id as a subagent dispatch and skip emitting
    `tool_invoked` / `tool_returned` for it), then closes the open
    parent turn so its `assistant_message` lands before
    `subagent_invoked` (spec §3 ordering: assistant_message MUST precede
    subagent_invoked). Sibling dispatches in the same parallel batch
    parent under the same just-closed turn via
    `state.last_dispatch_turn_span_id`. The dispatch's input is read
    from the parent turn's buffered content (still populated after
    `_close_turn`, which empties only on the next `_open_turn`)."""
    if not message.tool_use_id:
        return
    tool_use_id = message.tool_use_id
    # Mark the id as a subagent dispatch BEFORE closing the turn so
    # `_close_turn`'s bracketing pass skips it (no spurious tool_invoked).
    state.task_info[tool_use_id] = TaskInfo(
        task_id=message.task_id,
        description=message.description,
        task_type=message.task_type,
    )
    # Look up the dispatch ToolUseBlock by id in the buffered (or
    # just-flushed) parent turn content. Synthesize a minimal one if it
    # wasn't observed -- the wire event still validates.
    dispatch_block: AVPToolUseBlock | None = None
    for block in state.turn_content:
        if isinstance(block, AVPToolUseBlock) and block.id == tool_use_id:
            dispatch_block = block
            break
    if dispatch_block is None:
        dispatch_block = AVPToolUseBlock(id=tool_use_id, name="Agent", input={})
    # Capture parent turn span before close clears it. Fall back to a
    # sibling-dispatch's captured span (parallel batch) or the agent
    # span if neither is available.
    parent_span_id = state.current_turn_span_id or state.last_dispatch_turn_span_id
    if state.current_turn_span_id is not None:
        await _close_turn(state)
        state.last_dispatch_turn_span_id = parent_span_id
    if parent_span_id is None:
        parent_span_id = state.agent_span_id or ZERO_SPAN_ID
    await _emit_subagent_invoked(
        state,
        parent_span_id=parent_span_id,
        block=dispatch_block,
    )


async def _on_task_notification(state: RunState, message: TaskNotificationMessage) -> None:
    """Drive `subagent_returned` / `subagent_failed` from the SDK
    lifecycle. `status == "failed"` produces `subagent_failed`;
    `completed` / `stopped` produce `subagent_returned` with the
    matching `StopReason`. Updates `TaskInfo` with the terminal
    payload first so the close helper picks up the summary / usage."""
    if not message.tool_use_id:
        return
    info = state.task_info.get(message.tool_use_id)
    if info is None:
        # TaskNotification without a preceding TaskStarted: synthesize a
        # minimal TaskInfo so the close still has something to read.
        info = TaskInfo(task_id=message.task_id, description="")
        state.task_info[message.tool_use_id] = info
    info.status = message.status
    info.summary = message.summary
    info.usage = dict(message.usage) if message.usage is not None else None
    await _emit_subagent_returned_or_failed(
        state,
        tool_use_id=message.tool_use_id,
        result_text=message.summary or "",
    )


# ---------------------------------------------------------------------------
# Public dispatch entry point
# ---------------------------------------------------------------------------


async def handle_message(state: RunState, message: Message) -> None:
    """Dispatch one SDK message to the appropriate AVP emitter. Mutates state."""
    if isinstance(message, AssistantMessage):
        await _on_assistant(state, message)
    elif isinstance(message, UserMessage):
        await _on_user(state, message)
    elif isinstance(message, ResultMessage):
        await _on_result(state, message)
    elif isinstance(message, TaskStartedMessage):
        await _on_task_started(state, message)
    elif isinstance(message, TaskNotificationMessage):
        await _on_task_notification(state, message)
    # TaskProgressMessage, plain SystemMessage (init/etc), MirrorErrorMessage,
    # StreamEvent, RateLimitEvent: drop. Per checklist: honest-silent beats
    # fabricated events.
