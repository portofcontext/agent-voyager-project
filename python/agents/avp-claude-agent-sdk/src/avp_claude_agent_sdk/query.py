"""AVP-compliant wrapper around `claude_agent_sdk.query`."""

import uuid
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from claude_agent_sdk import Transport
from claude_agent_sdk import query as _sdk_query
from claude_agent_sdk.types import ClaudeAgentOptions, Message

from avp._envelope import ZERO_SPAN_ID, new_span_id, new_trace_id
from avp.agent import AVPAgentSink, EventSink, stdio_sink
from avp.trajectory import (
    AgentDescribedData,
    AgentDescribedEvent,
    AgentStartedData,
    AgentStartedEvent,
    RunRequestedData,
    RunRequestedEvent,
)
from avp_claude_agent_sdk._translator import descriptor_from_options


async def query(
    *,
    prompt: str | AsyncIterable[dict[str, Any]],
    options: ClaudeAgentOptions | None = None,
    transport: Transport | None = None,
    sink: EventSink | None = None,
) -> AsyncIterator[Message]:
    """Drop-in wrapper for `claude_agent_sdk.query` that emits an AVP trajectory.

    Same call surface as `claude_agent_sdk.query` plus a `sink` kwarg.
    `sink` defaults to `avp.agent.stdio_sink` (NDJSON to stdout); pass a
    custom :data:`avp.agent.EventSink` to capture events elsewhere.
    """
    if options is None:
        options = ClaudeAgentOptions()

    avp = AVPAgentSink(sink or stdio_sink)

    trace_id = new_trace_id()
    run_id = str(uuid.uuid4())
    prompt_text = prompt if isinstance(prompt, str) else None

    # § 2.1 — run prelude: run_requested, agent_described, agent_started.
    # All three are span-tree roots (parent_span_id = ZERO); agent_started's
    # span_id becomes the agent span that subsequent run events nest under.
    #
    # `query()` is the library-invocation path with no Commission, so
    # run_requested omits `avp.commission` and `avp.supervisor.*` entirely
    # (per §2.1, absence — not `"unknown"` — is the canonical signal). The
    # event still anchors the run via `subject = run_id` + span triple; the
    # agent's invocation surface is advertised on `agent_described` instead.
    await avp.emit(
        RunRequestedEvent(
            subject=run_id,
            data=RunRequestedData(
                trace_id=trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
            ),
        )
    )

    descriptor = descriptor_from_options(prompt_text, options)
    await avp.emit(
        AgentDescribedEvent(
            subject=run_id,
            data=AgentDescribedData(
                trace_id=trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
                avp_descriptor=descriptor,
            ),
        )
    )

    # No Commission → no merge step. The descriptor IS the settled state,
    # so its tools / mcp_servers / skills / subagents / prompts pass
    # through verbatim onto agent_started (§2.1 "merged-state snapshot").
    agent_span_id = new_span_id()
    await avp.emit(
        AgentStartedEvent(
            subject=run_id,
            data=AgentStartedData(
                trace_id=trace_id,
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

    async for message in _sdk_query(prompt=prompt, options=options, transport=transport):
        yield message
