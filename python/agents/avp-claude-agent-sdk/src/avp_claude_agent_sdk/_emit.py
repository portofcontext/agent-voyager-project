"""AVP event emitters for the Claude Agent SDK adapter.

Currently covers the prelude only (`run_requested`, `agent_described`,
`agent_started`); per-message handlers and turn lifecycle are
reintroduced incrementally.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    ContentBlock,
    McpStatusResponse,
    Message,
    ServerToolResultBlock,
    ServerToolUseBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from avp._envelope import ZERO_SPAN_ID, new_span_id
from avp.content import AVPContentBlock
from avp.content import ServerToolResultBlock as AVPServerToolResultBlock
from avp.content import ServerToolUseBlock as AVPServerToolUseBlock
from avp.content import TextBlock as AVPTextBlock
from avp.content import ThinkingBlock as AVPThinkingBlock
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
    Usage,
)
from avp_claude_agent_sdk._runstate import RunState, Turn
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


# ---------------------------------------------------------------------------
# Per-message handlers
# ---------------------------------------------------------------------------


async def _on_assistant(state: RunState, message: AssistantMessage) -> None:
    """Handle one AssistantMessage chunk.

    Drains the open turn on a new `message_id`, then opens (if needed)
    and extends the current turn with the chunk's content, model,
    stop_reason, and usage. Subagent-interior chunks
    (`parent_tool_use_id is not None`) are skipped under the in-process
    subagent fallback (spec §5.6).
    """
    if message.parent_tool_use_id is not None:
        # parent_tool_use_id indicates it is a subagent assistant msg
        return

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

    state.turn.content.extend(_translate_blocks(message.content))
    if state.turn.response_model is None:
        state.turn.response_model = message.model
    if message.stop_reason:
        state.turn.stop_reason = message.stop_reason
    if message.usage:
        state.turn.usage = _usage_from_dict(message.usage)


# ---------------------------------------------------------------------------
# Public dispatch entry point
# ---------------------------------------------------------------------------


async def handle_message(state: RunState, message: Message) -> None:
    """Dispatch one SDK message to the appropriate AVP emitter. Mutates state."""
    if isinstance(message, AssistantMessage):
        await _on_assistant(state, message)
    # elif isinstance(message, UserMessage):
    #     await _on_user(state, message)
    # elif isinstance(message, ResultMessage):
    #     await _on_result(state, message)
    # elif isinstance(message, TaskStartedMessage):
    #     await _on_task_started(state, message)
    # elif isinstance(message, TaskNotificationMessage):
    #     await _on_task_notification(state, message)
    # TaskProgressMessage, plain SystemMessage (init/etc), MirrorErrorMessage,
    # StreamEvent, RateLimitEvent: drop. Honest-silent beats fabricated events.
