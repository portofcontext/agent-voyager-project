"""Stateless AVP event emitters and SDK message dispatcher.

Low-level emitters (`emit_prelude`, `emit_model_turn_started`, ...) take a
`RunState` and emit exactly the events their name implies, mutating state as
needed. `handle_message` is the single entry point for the SDK stream: it
dispatches each raw SDK message to the right emitter and is reusable across
both the `query` patch and the `ClaudeSDKClient` patch (Stage 3).

Stage 1: prelude, model_turn_started, agent_stopped, merge gate.
Stage 1 (post-review): text_emitted, reasoning_emitted, model_turn_ended.
Stage 2: tool_invoked, tool_returned, tool_failed, subagent_invoked/returned.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk.types import ClaudeAgentOptions

from avp._envelope import ZERO_SPAN_ID, new_span_id
from avp.trajectory import (
    AgentDescribedData,
    AgentDescribedEvent,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    RunRequestedData,
    RunRequestedEvent,
    StopReason,
)
from avp_claude_agent_sdk._runstate import RunState
from avp_claude_agent_sdk._translator import descriptor_from_options

# ---------------------------------------------------------------------------
# Prelude
# ---------------------------------------------------------------------------


async def emit_prelude(
    state: RunState,
    prompt: str | None,
    options: ClaudeAgentOptions,
) -> None:
    """Emit run_requested, agent_described, agent_started. Sets state.agent_span_id."""
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

    descriptor = descriptor_from_options(prompt, options)
    await state.sink(
        AgentDescribedEvent(
            subject=state.run_id,
            data=AgentDescribedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
                avp_descriptor=descriptor,
            ),
        )
    )

    agent_span_id = new_span_id()
    state.agent_span_id = agent_span_id
    await state.sink(
        AgentStartedEvent(
            subject=state.run_id,
            data=AgentStartedData(
                trace_id=state.trace_id,
                span_id=agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                gen_ai_provider_name="anthropic",
                gen_ai_operation_name="invoke_agent",
                gen_ai_request_model=descriptor.default_model,
                prompt=descriptor.prompt,
                system_prompt=descriptor.system_prompt,
                tools=descriptor.tools,
                mcp_servers=descriptor.mcp_servers,
                skills=descriptor.skills,
                subagents=descriptor.subagents,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Per-turn
# ---------------------------------------------------------------------------


async def emit_model_turn_started(state: RunState, step: int) -> None:
    """Emit model_turn_started and update state.current_turn_span_id."""
    span_id = new_span_id()
    state.current_turn_span_id = span_id
    await state.sink(
        ModelTurnStartedEvent(
            subject=state.run_id,
            data=ModelTurnStartedData(
                trace_id=state.trace_id,
                span_id=span_id,
                parent_span_id=state.agent_span_id,
                step=step,
                gen_ai_request_stream=True,
            ),
        )
    )


async def emit_agent_stopped(
    state: RunState,
    reason: StopReason,
    *,
    output: Any = None,
) -> None:
    """Emit agent_stopped. Always the last event on the wire."""
    await state.sink(
        AgentStoppedEvent(
            subject=state.run_id,
            data=AgentStoppedData(
                trace_id=state.trace_id,
                span_id=new_span_id(),
                parent_span_id=state.agent_span_id or ZERO_SPAN_ID,
                avp_reason=reason,
                avp_output=output,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Per-message handlers (called by handle_message)
# ---------------------------------------------------------------------------


async def _on_assistant(state: RunState, _message: Any) -> None:
    # Merge gate: consecutive AssistantMessages without an intervening
    # UserMessage(ToolResult) are the same LLM call (e.g. thinking block
    # followed by text block). Mirror Braintrust's `next_llm_start` check.
    if state.current_turn_span_id is not None and not state.tool_result_arrived:
        return
    state.step += 1
    state.tool_result_arrived = False
    await emit_model_turn_started(state, state.step)


async def _on_user(state: RunState, message: Any) -> None:
    content = getattr(message, "content", None) or []
    if any(type(b).__name__ == "ToolResultBlock" for b in content):
        state.tool_result_arrived = True


async def _on_result(state: RunState, message: Any) -> None:
    is_error = getattr(message, "is_error", False)
    reason = StopReason.error if is_error else StopReason.converged
    output = getattr(message, "result", None)
    await emit_agent_stopped(state, reason, output=output)


# ---------------------------------------------------------------------------
# Public dispatch entry point
# ---------------------------------------------------------------------------


async def handle_message(state: RunState, message: Any) -> None:
    """Dispatch one SDK message to the appropriate AVP emitter. Mutates state.

    Reusable across query patch (Stage 1) and ClaudeSDKClient patch (Stage 3).
    Uses class-name dispatch (not isinstance) to stay decoupled from SDK imports
    and resilient to SDK class hierarchy changes.
    """
    msg_type = type(message).__name__
    if msg_type == "AssistantMessage":
        await _on_assistant(state, message)
    elif msg_type == "UserMessage":
        await _on_user(state, message)
    elif msg_type == "ResultMessage":
        await _on_result(state, message)
    # TODO: SystemMessage, RateLimitEvent, StreamEvent: Stage 2+
