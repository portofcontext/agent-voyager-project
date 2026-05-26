"""avp.gen_ai — Project AVP trajectory events into OpenTelemetry GenAI attributes.

OTel GenAI semantic conventions registry:
  https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/

AVP's wire format carries attributes under its own `avp.*` namespace.
Consumers forwarding the same data into an OTel-native backend (OTLP
collectors, Honeycomb / Datadog / Grafana GenAI views) call
`to_gen_ai_attrs(event)` to derive a dict of `gen_ai.*` attributes ready
to attach to a span. The AVP wire stays put; this is the projection
layer.

The projection is one-way (AVP wire → OTel attrs), one event at a time.
AVP-specific fields without an OTel equivalent (`avp.cost_usd`,
`avp.refusal.category`, ...) are intentionally NOT projected. See
`FOUNDATIONS.md` for the mapping table and rationale.

## Un-projected OTel GenAI attributes

The following registry attributes are NOT in the projection:

**Spec gaps — present in OTel, absent from AVP wire today:**

  - Sampling parameters: `gen_ai.request.{max_tokens, temperature, top_p,
    top_k, frequency_penalty, presence_penalty, seed, stop_sequences,
    choice_count, stream}`. Belong on `Commission` / `agent_started`.
  - `gen_ai.response.id` — provider-assigned response id (e.g. OpenAI's
    `id`). Would live on `AssistantMessageData`.
  - `gen_ai.tool.{type, description, definitions}` — tool classification
    and per-tool metadata. AVP has descriptions on
    `agent_started.tools[]` decls but not on dispatch events.

**Projector-shape limitation:**

  - `gen_ai.input.messages` — requires the prior event stream, not a
    single event. Build via `avp.history.to_messages(events_so_far)`
    and attach manually when entering an `assistant_message` span.

**Out of scope for AVP (see [trajectory.md §1.1](../../../spec/v0.1/trajectory.md) non-goals):**

  - Retrieval: `gen_ai.retrieval.{query.text, documents}` — RAG-specific.
  - Evaluation: `gen_ai.evaluation.{name, score.value, score.label,
    explanation}` — post-hoc annotation, not runtime.
  - Workflow / data source: `gen_ai.{workflow.name, data_source.id}` —
    supervisor-framework concerns above the wire.
  - Embeddings: `gen_ai.request.encoding_formats`,
    `gen_ai.embeddings.dimension.count` — AVP isn't designed for
    embedding workloads.
  - Per-token granularity: `gen_ai.token.type`.
  - Output modality: `gen_ai.output.type`.
"""

from __future__ import annotations

from typing import Any

from avp.trajectory import (
    AgentDescribedEvent,
    AgentStartedEvent,
    AssistantMessageEvent,
    Event,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)


def _drop_none(attrs: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in attrs.items() if v is not None}


def to_gen_ai_attrs(event: Event) -> dict[str, Any]:
    """Project an AVP `Event` into a dict of OTel `gen_ai.*` attributes.

    Keys are the OTel GenAI registry names; values are passed through
    from the AVP payload unchanged (no unit conversion). Returns `{}`
    for events with no GenAI projection (`run_requested`, `agent_stopped`,
    `mcp_*`, `error_occurred`, `UnknownEvent`).
    """
    if isinstance(event, AgentStartedEvent):
        d = event.data
        return _drop_none(
            {
                "gen_ai.provider.name": d.provider_name,
                "gen_ai.operation.name": d.operation_name,
                "gen_ai.request.model": d.request_model,
                "gen_ai.conversation.id": d.thread_id,
                "gen_ai.system_instructions": d.system_prompt,
            }
        )

    if isinstance(event, AssistantMessageEvent):
        d = event.data
        u = d.usage
        output_messages = [
            {
                "role": "assistant",
                "content": [
                    b.model_dump(by_alias=True, exclude_none=True, mode="json") for b in d.content
                ],
            }
        ]
        return _drop_none(
            {
                "gen_ai.provider.name": d.provider_name,
                "gen_ai.request.model": d.request_model,
                "gen_ai.response.model": d.response_model,
                "gen_ai.response.finish_reasons": d.response_finish_reasons,
                "gen_ai.response.time_to_first_chunk": d.response_time_to_first_chunk,
                "gen_ai.usage.input_tokens": u.input_tokens,
                "gen_ai.usage.output_tokens": u.output_tokens,
                "gen_ai.usage.cache_read.input_tokens": u.cache_read_input_tokens,
                "gen_ai.usage.cache_creation.input_tokens": u.cache_creation_input_tokens,
                "gen_ai.usage.reasoning.output_tokens": u.reasoning_output_tokens,
                "gen_ai.output.messages": output_messages,
            }
        )

    if isinstance(event, ToolInvokedEvent):
        d = event.data
        return {
            "gen_ai.tool.name": d.tool_name,
            "gen_ai.tool.call.id": d.tool_call_id,
            "gen_ai.tool.call.arguments": d.tool_input,
        }

    if isinstance(event, ToolReturnedEvent):
        d = event.data
        return {
            "gen_ai.tool.name": d.tool_name,
            "gen_ai.tool.call.id": d.tool_call_id,
            "gen_ai.tool.call.result": d.tool_result.content,
        }

    if isinstance(event, SubagentInvokedEvent):
        d = event.data
        return _drop_none(
            {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": d.subagent_name,
                "gen_ai.agent.description": d.subagent_description,
                "gen_ai.agent.id": d.subagent_run_id,
            }
        )

    if isinstance(event, SubagentReturnedEvent):
        return {"gen_ai.agent.name": event.data.subagent_name}

    if isinstance(event, AgentDescribedEvent):
        desc = event.data.descriptor
        return {
            "gen_ai.agent.name": desc.agent_name,
            "gen_ai.agent.version": desc.agent_version,
        }

    return {}


__all__ = ["to_gen_ai_attrs"]
