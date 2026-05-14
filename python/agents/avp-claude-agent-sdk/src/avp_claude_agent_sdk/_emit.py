"""Stateless AVP event emitters.

Each helper accepts a RunState and zero or more SDK message arguments,
then emits the corresponding AVP event(s) via `state.sink`. All mutable
state lives in RunState; nothing is stored here.

Stage 1: prelude (run_requested, agent_described, agent_started) and
    model_turn_started.
Stage 1 (post-review): text_emitted, model_turn_ended, agent_stopped.
Stage 2: tool / subagent emitters.
"""

from __future__ import annotations

from claude_agent_sdk.types import ClaudeAgentOptions

from avp._envelope import ZERO_SPAN_ID, new_span_id
from avp.trajectory import (
    AgentDescribedData,
    AgentDescribedEvent,
    AgentStartedData,
    AgentStartedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    RunRequestedData,
    RunRequestedEvent,
)
from avp_claude_agent_sdk._runstate import RunState
from avp_claude_agent_sdk._translator import descriptor_from_options


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
