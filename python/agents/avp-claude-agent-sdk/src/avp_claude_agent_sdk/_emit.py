"""AVP event emitters for the Claude Agent SDK adapter.

Currently covers the prelude only (`run_requested`, `agent_described`,
`agent_started`); per-message handlers and turn lifecycle are
reintroduced incrementally.
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
    ServerToolResultBlock,
    ServerToolUseBlock,
    TaskNotificationMessage,
    TaskStartedMessage,
    TaskUsage,
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
from avp.trajectory import (
    AgentDescribedData,
    AgentDescribedEvent,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
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
from avp_claude_agent_sdk._runstate import RunState, TaskInfo, ToolSpan, Turn
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


async def emit_run_requested(state: RunState) -> None:
    """First event of the trajectory. Anchors the run."""
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
    """Pre-Commission capability surface (probe-derived descriptor).

    `init_data` from a probe `SystemMessage(init)`; `status` from the
    probe's `get_mcp_status()`. When `init_data is None`, the descriptor
    carries identity + default_model only -- still spec-conformant.
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
    """Merged-state snapshot for the run. Sets `state.agent_span_id` so
    subsequent turn / tool events parent under it."""
    agent_span_id = new_span_id()
    state.agent_span_id = agent_span_id
    sdk_session_id = init_data.get("session_id") if init_data else None
    meta = {"claude_agent_sdk.session_id": sdk_session_id} if sdk_session_id else None
    await state.sink(
        AgentStartedEvent(
            subject=state.run_id,
            data=AgentStartedData(
                trace_id=state.trace_id,
                span_id=agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                meta=meta,
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


async def emit_agent_stopped(
    state: RunState,
    reason: StopReason,
    *,
    output: Any = None,
) -> None:
    """Final event of the trajectory. Idempotent via `state.stopped` so
    ResultMessage handling, disconnect fallbacks, and exception paths
    can all call this safely without double-emitting. Drains any open
    turn first so the last `assistant_message` lands before the close
    regardless of which path triggered the stop."""
    if state.stopped:
        return
    if state.agent_span_id is not None:
        await state.drain()
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
# SDK → AVP translation helpers
# ---------------------------------------------------------------------------


def _translate_blocks(blocks: list[ContentBlock]) -> list[AVPContentBlock]:
    """SDK content blocks → AVP content blocks. Drops unknown subtypes
    silently (honest-silent beats fabricated). `ToolResultBlock` is not
    translated here -- it surfaces as a `tool_returned` event, not as
    inline content.

    `ServerToolResultBlock` doesn't carry `name` (only its paired
    `ServerToolUseBlock` does); a single in-order pass tracks the most
    recent server-tool name per `tool_use_id` and back-fills it.
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


def _usage_from_dict(usage: dict[str, Any]) -> Usage:
    """Project the SDK's `AssistantMessage.usage` dict onto AVP `Usage`.

    The SDK reports the API call's response totals (duplicated on every
    chunk of one `message_id`), so overwriting on each chunk converges
    to the inference's true totals by the time the turn drains.
    """
    return Usage(
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_input_tokens=int(usage.get("cache_read_input_tokens") or 0) or None,
        cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens") or 0) or None,
    )


def _dispatch_target(tool_name: str) -> Literal["mcp_server", "local"]:
    """Wire discriminator for `tool_invoked`. The Claude Agent SDK
    namespaces MCP tools as `mcp__<server>__<tool>`; everything else is
    a CLI built-in, server tool, or local hook."""
    return "mcp_server" if tool_name.startswith("mcp__") else "local"


# ---------------------------------------------------------------------------
# Per-message handlers
# ---------------------------------------------------------------------------


async def _on_assistant(state: RunState, message: AssistantMessage) -> None:
    """Handle one AssistantMessage chunk.

    Drains the open turn on a new `message_id`, then opens (if needed)
    and extends the current turn with the chunk's content, model,
    stop_reason, and usage. Emits `tool_invoked` for each `ToolUseBlock`
    / `ServerToolUseBlock` (Task dispatches skipped -- those become
    `subagent_invoked` via `TaskStartedMessage`) and `tool_returned` for
    each `ServerToolResultBlock` (server tools complete inline in the
    same response). Subagent-interior chunks
    (`parent_tool_use_id is not None`) are skipped under the in-process
    subagent fallback (spec §5.6).
    """
    if message.parent_tool_use_id is not None:
        return

    # The Claude CLI fans one API response's content blocks out as one
    # AssistantMessage per block, all stamped with the same `message_id`.
    # One AVP turn = one inference = one `message_id`, so multiple SDK
    # chunks merge into the open turn; a different non-None `message_id`
    # is the boundary that closes the prior inference.
    next_step = 1
    if (
        state.turn is not None
        and message.message_id is not None
        and message.message_id != state.turn.message_id
    ):
        drained = await state.drain()
        if drained is not None:
            next_step = drained.step + 1

    if state.turn is None:
        state.turn = Turn(message_id=message.message_id, step=next_step)

    state.turn.meta_chunks_merged += 1
    translated = _translate_blocks(message.content)
    state.turn.content.extend(translated)
    for block in translated:
        if isinstance(block, AVPToolUseBlock):
            # Task dispatches surface as subagent_invoked (driven by
            # TaskStartedMessage), not tool_invoked.
            if block.name == "Task":
                continue
            _buffer_tool_invoked(state, block.id, block.name, block.input)
        elif isinstance(block, AVPServerToolUseBlock):
            _buffer_tool_invoked(state, block.id, block.name, block.input)
        elif isinstance(block, AVPServerToolResultBlock):
            # Server tools execute in the model's runtime and return
            # inline in the same response, so bracket within this chunk.
            _buffer_tool_returned(
                state,
                block.tool_use_id,
                AVPToolResultBlock(
                    tool_use_id=block.tool_use_id,
                    content=_normalize_tool_result_content(block.content),
                ),
            )

    if state.turn.response_model is None:
        state.turn.response_model = message.model
    if message.stop_reason:
        state.turn.stop_reason = message.stop_reason
    if message.usage:
        state.turn.usage = _usage_from_dict(message.usage)
        state.turn.meta_service_tier = (
            message.usage.get("service_tier") or state.turn.meta_service_tier
        )
        cache_creation = message.usage.get("cache_creation") or {}
        if isinstance(cache_creation, dict):
            state.turn.meta_cache_creation_5m = int(
                cache_creation.get("ephemeral_5m_input_tokens") or 0
            )
            state.turn.meta_cache_creation_1h = int(
                cache_creation.get("ephemeral_1h_input_tokens") or 0
            )


def _buffer_tool_invoked(
    state: RunState,
    tool_use_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> None:
    """Mint a span, register a `ToolSpan` for later pairing, and append
    a `tool_invoked` to the open turn's emissions. No-op if no turn open.
    """
    if state.turn is None:
        return
    span_id = new_span_id()
    state.turn.tool_spans[tool_use_id] = ToolSpan(
        span_id=span_id,
        step=state.turn.step,
        name=tool_name,
        started_at=time.monotonic(),
    )
    state.turn.emissions.append(
        ToolInvokedEvent(
            subject=state.run_id,
            data=ToolInvokedData(
                trace_id=state.trace_id,
                span_id=span_id,
                parent_span_id=state.turn.span_id,
                step=state.turn.step,
                tool_call_id=tool_use_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_dispatch_target=_dispatch_target(tool_name),
            ),
        )
    )


def _buffer_tool_returned(
    state: RunState,
    tool_use_id: str,
    tool_result: AVPToolResultBlock,
) -> None:
    """Pop the matching `ToolSpan` and append a paired `tool_returned`
    to the open turn's emissions. Silently drops if no matching
    invocation: subagent task results (handled by `subagent_returned`),
    unknown ids, or no open turn."""
    if state.turn is None:
        return
    span = state.turn.tool_spans.pop(tool_use_id, None)
    if span is None:
        return
    duration_ms = max(0, int((time.monotonic() - span.started_at) * 1000))
    state.turn.emissions.append(
        ToolReturnedEvent(
            subject=state.run_id,
            data=ToolReturnedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=span.span_id,
                step=span.step,
                tool_call_id=tool_use_id,
                tool_name=span.name,
                duration_ms=duration_ms,
                tool_result=tool_result,
            ),
        )
    )


def _normalize_tool_result_content(content: Any) -> str | list[Any]:
    """Coerce arbitrary tool-result payloads into AVP `ToolResultBlock.content`.

    Strings pass through; `None` becomes `""`; anything else is
    JSON-encoded (or stringified as a last resort) so the AVP block
    validates while preserving the payload lossily-but-observably."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, default=str)
    except (TypeError, ValueError):
        return str(content)


async def _on_user(state: RunState, message: UserMessage) -> None:
    """Handle one UserMessage: each `ToolResultBlock` in `content`
    closes a prior `tool_invoked`. Subagent-interior UserMessages and
    tool results that paired against a Task dispatch (subagent return
    path) are skipped."""
    if message.parent_tool_use_id is not None:
        return
    if state.turn is None:
        return
    content = message.content if isinstance(message.content, list) else []
    tool_results = [b for b in content if isinstance(b, ToolResultBlock)]
    if not tool_results:
        return
    # `UserMessage.tool_use_result` is the SDK's structured-payload
    # channel paired with the human-readable `ToolResultBlock.content`
    # string. It's per-message, so attribution is only unambiguous when
    # there's exactly one result block; multi-result messages drop it
    # to avoid mis-attribution. Wrap non-dict payloads so the AVP field
    # still validates.
    structured: dict[str, Any] | None
    if len(tool_results) == 1 and message.tool_use_result is not None:
        raw = message.tool_use_result
        structured = raw if isinstance(raw, dict) else {"result": raw}
    else:
        structured = None
    for block in tool_results:
        if block.tool_use_id in state.turn.tasks:
            # Subagent dispatch's synthetic tool result; subagent_returned covers it.
            continue
        _buffer_tool_returned(
            state,
            block.tool_use_id,
            AVPToolResultBlock(
                tool_use_id=block.tool_use_id,
                content=_normalize_tool_result_content(block.content),
                structured_content=structured,
                is_error=block.is_error,
            ),
        )


# ---------------------------------------------------------------------------
# Subagent (Task) lifecycle
# ---------------------------------------------------------------------------


_TASK_STATUS_TO_REASON: dict[str, StopReason] = {
    "completed": StopReason.converged,
    "stopped": StopReason.interrupted,
}


def _task_usage_to_subagent_usage(usage: TaskUsage | None) -> SubagentUsage | None:
    """Project a `TaskUsage` onto AVP `SubagentUsage`.

    `TaskUsage` carries `{total_tokens, tool_uses, duration_ms}` with no
    input/output split or cost. AVP required fields stay at 0 (honest
    sentinel -- we don't know); the raw triple rides along as extras
    (`SubagentUsage` permits open keys).
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


def _subagent_input(state_turn_content: list[AVPContentBlock], tool_use_id: str) -> dict[str, Any]:
    """Find the parent's Task `ToolUseBlock` in the open turn's content
    and return its input dict (the subagent's prompt / subagent_type /
    description). Empty dict if not found (defensive)."""
    for block in state_turn_content:
        if isinstance(block, AVPToolUseBlock) and block.id == tool_use_id:
            return block.input
    return {}


async def _on_task_started(state: RunState, message: TaskStartedMessage) -> None:
    """Buffer a `subagent_invoked` onto the open turn's emissions.

    Fires when the CLI spawns a Task subagent. We record the dispatch
    in `state.turn.tasks` for `_on_task_notification` to pair against.
    The matching `ToolUseBlock` (in `state.turn.content`) supplies
    `subagent_input`.
    """
    if state.turn is None or not message.tool_use_id:
        return
    span_id = new_span_id()
    task_type = message.task_type or "Task"
    state.turn.tasks[message.tool_use_id] = TaskInfo(
        span_id=span_id,
        parent_span_id=state.turn.span_id,
        step=state.turn.step,
        task_type=task_type,
        started_at=time.monotonic(),
    )
    state.turn.emissions.append(
        SubagentInvokedEvent(
            subject=state.run_id,
            data=SubagentInvokedData(
                trace_id=state.trace_id,
                span_id=span_id,
                parent_span_id=state.turn.span_id,
                step=state.turn.step,
                subagent_name=task_type,
                subagent_invocation_id=message.tool_use_id,
                subagent_input=_subagent_input(state.turn.content, message.tool_use_id),
            ),
        )
    )


async def _on_task_notification(state: RunState, message: TaskNotificationMessage) -> None:
    """Buffer the matching `subagent_returned` (completed / stopped) or
    `subagent_failed` (failed) onto the open turn's emissions. No-op if
    the dispatch wasn't recorded (e.g. the parent turn drained early)."""
    if state.turn is None or not message.tool_use_id:
        return
    info = state.turn.tasks.pop(message.tool_use_id, None)
    if info is None:
        return
    duration_ms = max(0, int((time.monotonic() - info.started_at) * 1000))
    summary = message.summary or ""
    if message.status == "failed":
        state.turn.emissions.append(
            SubagentFailedEvent(
                subject=state.run_id,
                data=SubagentFailedData(
                    trace_id=state.trace_id,
                    span_id=new_span_id(),
                    parent_span_id=info.span_id,
                    step=info.step,
                    subagent_name=info.task_type,
                    subagent_invocation_id=message.tool_use_id,
                    duration_ms=duration_ms,
                    subagent_error=summary,
                ),
            )
        )
        return
    reason = _TASK_STATUS_TO_REASON.get(message.status, StopReason.converged)
    state.turn.emissions.append(
        SubagentReturnedEvent(
            subject=state.run_id,
            data=SubagentReturnedData(
                trace_id=state.trace_id,
                # span_id matches subagent_invoked (same frame, closed).
                span_id=info.span_id,
                # Parent under the frame's parent (turn span), not the frame itself.
                parent_span_id=info.parent_span_id,
                step=info.step,
                subagent_name=info.task_type,
                subagent_invocation_id=message.tool_use_id,
                duration_ms=duration_ms,
                subagent_result_text=summary,
                subagent_reason=reason,
                subagent_usage=_task_usage_to_subagent_usage(message.usage),
            ),
        )
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
    elif isinstance(message, TaskStartedMessage):
        await _on_task_started(state, message)
    elif isinstance(message, TaskNotificationMessage):
        await _on_task_notification(state, message)
    # elif isinstance(message, ResultMessage):
    #     await _on_result(state, message)
    # SystemMessage, TaskProgressMessage, MirrorErrorMessage, StreamEvent,
    # RateLimitEvent: drop. Honest-silent beats fabricated events.
