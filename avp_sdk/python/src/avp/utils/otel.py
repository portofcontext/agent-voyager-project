"""Convert a Trajectory to OpenTelemetry spans with GenAI attributes.

Attribute names follow the OpenTelemetry GenAI semantic conventions
(https://github.com/open-telemetry/semantic-conventions-genai), which are in
Development status and have no release yet; this module follows `main` as of
commit 6f98aef (2026-10-30).

| Span | From | Parent |
|---|---|---|
| `invoke_agent {agent}` | `agent_started` to `agent_stopped` | the `parent` passed in, if any |
| `chat {model}` | `assistant_message`, starting `duration_ms` before its `time` | its subagent, or the run |
| `execute_tool {tool}` | `tool_invoked` to `tool_returned` | the response with its `tool_use`, else its subagent or the run |
| `invoke_agent {subagent}` | `subagent_invoked` to `subagent_returned` | the tool call that started it, else its subagent or the run |

IDs come from `run_id` and the events' IDs, so the same Trajectory always gives
the same spans. A span the Trajectory never closes ends at its last event.

The spans are plain records, so the SDK needs no OpenTelemetry package: create
spans from them with the OpenTelemetry SDK, or send `to_otlp_json`'s output to
a collector's `/v1/traces` endpoint.
"""

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, JsonValue

from avp._base import AVP_VERSION
from avp.trajectory import (
    AgentDescribedEvent,
    AgentStartedEvent,
    AgentStoppedEvent,
    AssistantMessageEvent,
    Event,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    ToolUseBlock,
)

Attribute = str | int | float | bool | list[str]


class Span(BaseModel):
    """One OpenTelemetry span."""

    name: str
    kind: Literal["internal", "client"]
    trace_id: str
    """32 hex digits."""
    span_id: str
    """16 hex digits."""
    parent_span_id: str | None = None
    start: datetime
    end: datetime
    attributes: dict[str, Attribute]
    error: bool = False
    """The span's status is `ERROR`."""


def _hex(digits: int, *parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:digits]


def _json(value: JsonValue) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _traceparent(parent: str) -> tuple[str, str]:
    """The trace ID and span ID of a W3C `traceparent`."""
    parts = parent.split("-")
    if len(parts) != 4 or len(parts[1]) != 32 or len(parts[2]) != 16:
        raise ValueError(f"not a W3C traceparent: {parent!r}")
    return parts[1], parts[2]


def to_spans(
    events: Iterable[Event], *, parent: str | None = None, include_content: bool = False
) -> list[Span]:
    """The spans for one run's events, in the order they start.

    `parent` is a W3C `traceparent`, such as the supervisor's, to put the run
    under. Without it the run starts its own trace. `include_content` adds the
    system prompt and tool arguments and results, which OpenTelemetry leaves
    out by default because they can hold sensitive data.
    """
    events = list(events)
    if not events:
        return []
    run_id = events[0].run_id
    trace_id, root_parent = _traceparent(parent) if parent else (_hex(32, run_id), None)
    last_time = max(event.time for event in events)

    def span_id(*key: str) -> str:
        return _hex(16, run_id, *key)

    run_span = span_id("run")
    agent_name = next(
        (e.data.descriptor.agent_name for e in events if isinstance(e, AgentDescribedEvent)),
        None,
    )
    spans: dict[str, Span] = {}
    tool_use_owner: dict[str, str] = {}  # tool_use id -> span of the response that made it

    def owner(subagent_invocation_id: str | None) -> str:
        if subagent_invocation_id is None:
            return run_span
        return span_id("subagent", subagent_invocation_id)

    def open_span(key: str, span: Span) -> None:
        spans[key] = span

    def close_span(key: str, time: datetime, error: bool) -> None:
        if key in spans:
            spans[key] = spans[key].model_copy(update={"end": time, "error": error})

    for event in events:
        if isinstance(event, AgentStartedEvent):
            data = event.data
            attributes: dict[str, Attribute] = {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.provider.name": data.model.provider,
                "gen_ai.request.model": data.model.id,
            }
            if agent_name:
                attributes["gen_ai.agent.name"] = agent_name
            if include_content and data.system_prompt:
                attributes["gen_ai.system_instructions"] = _json(
                    [{"type": "text", "content": data.system_prompt}]
                )
            open_span(
                "run",
                Span(
                    name=f"invoke_agent {agent_name}" if agent_name else "invoke_agent",
                    kind="internal",
                    trace_id=trace_id,
                    span_id=run_span,
                    parent_span_id=root_parent,
                    start=event.time,
                    end=last_time,
                    attributes=attributes,
                ),
            )
        elif isinstance(event, AgentStoppedEvent):
            close_span("run", event.time, event.data.reason == "error")
        elif isinstance(event, AssistantMessageEvent):
            data = event.data
            response_span = span_id("response", event.id)
            for block in data.content:
                if isinstance(block, ToolUseBlock):
                    tool_use_owner[block.id] = response_span
            usage = data.usage
            attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": data.model.provider,
                "gen_ai.request.model": data.model.id,
                "gen_ai.response.model": data.response_model or data.model.id,
                "gen_ai.usage.input_tokens": usage.input_tokens,
                "gen_ai.usage.output_tokens": usage.output_tokens,
            }
            optional: dict[str, Attribute | None] = {
                "gen_ai.response.finish_reasons": data.finish_reasons,
                "gen_ai.usage.cache_read.input_tokens": usage.cache_read_input_tokens,
                "gen_ai.usage.cache_write.input_tokens": usage.cache_creation_input_tokens,
                "gen_ai.usage.reasoning.output_tokens": usage.reasoning_output_tokens,
            }
            for name, value in optional.items():
                if value is not None:
                    attributes[name] = value
            open_span(
                f"response:{event.id}",
                Span(
                    name=f"chat {data.model.id}",
                    kind="client",
                    trace_id=trace_id,
                    span_id=response_span,
                    parent_span_id=owner(data.subagent_invocation_id),
                    start=event.time - timedelta(milliseconds=data.duration_ms),
                    end=event.time,
                    attributes=attributes,
                ),
            )
        elif isinstance(event, ToolInvokedEvent):
            data = event.data
            attributes = {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": data.tool_name,
                "gen_ai.tool.call.id": data.tool_call_id,
            }
            if include_content:
                attributes["gen_ai.tool.call.arguments"] = _json(data.tool_input)
            open_span(
                f"tool:{data.tool_call_id}",
                Span(
                    name=f"execute_tool {data.tool_name}",
                    kind="internal",
                    trace_id=trace_id,
                    span_id=span_id("tool", data.tool_call_id),
                    parent_span_id=tool_use_owner.get(
                        data.tool_call_id, owner(data.subagent_invocation_id)
                    ),
                    start=event.time,
                    end=last_time,
                    attributes=attributes,
                ),
            )
        elif isinstance(event, ToolReturnedEvent):
            data = event.data
            key = f"tool:{data.tool_call_id}"
            if include_content and key in spans:
                result = data.tool_result.model_dump(mode="json", exclude_none=True)
                spans[key].attributes["gen_ai.tool.call.result"] = _json(result["content"])
            close_span(key, event.time, bool(data.tool_result.is_error))
        elif isinstance(event, SubagentInvokedEvent):
            data = event.data
            tool_span = spans.get(f"tool:{data.invocation_id}")
            open_span(
                f"subagent:{data.invocation_id}",
                Span(
                    name=f"invoke_agent {data.subagent_name}",
                    kind="internal",
                    trace_id=trace_id,
                    span_id=span_id("subagent", data.invocation_id),
                    parent_span_id=(
                        tool_span.span_id if tool_span else owner(data.subagent_invocation_id)
                    ),
                    start=event.time,
                    end=last_time,
                    attributes={
                        "gen_ai.operation.name": "invoke_agent",
                        "gen_ai.agent.name": data.subagent_name,
                    },
                ),
            )
        elif isinstance(event, SubagentReturnedEvent):
            data = event.data
            close_span(
                f"subagent:{data.invocation_id}", event.time, data.subagent_reason == "error"
            )

    return sorted(spans.values(), key=lambda span: span.start)


def _otlp_value(value: Attribute) -> dict[str, JsonValue]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [{"stringValue": v} for v in value]}}
    return {"stringValue": value}


def _nanos(time: datetime) -> str:
    return str(int(time.timestamp()) * 1_000_000_000 + time.microsecond * 1_000)


def to_otlp_json(spans: Iterable[Span], *, service_name: str = "avp-agent") -> dict[str, Any]:
    """The spans as an OTLP/JSON `ExportTraceServiceRequest`, the body a
    collector's `/v1/traces` endpoint accepts."""
    otlp_spans: list[JsonValue] = []
    for span in spans:
        otlp: dict[str, JsonValue] = {
            "traceId": span.trace_id,
            "spanId": span.span_id,
            "name": span.name,
            "kind": 3 if span.kind == "client" else 1,
            "startTimeUnixNano": _nanos(span.start),
            "endTimeUnixNano": _nanos(span.end),
            "attributes": [{"key": k, "value": _otlp_value(v)} for k, v in span.attributes.items()],
            "status": {"code": 2 if span.error else 0},
        }
        if span.parent_span_id:
            otlp["parentSpanId"] = span.parent_span_id
        otlp_spans.append(otlp)
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": service_name}}]
                },
                "scopeSpans": [
                    {"scope": {"name": "avp", "version": AVP_VERSION}, "spans": otlp_spans}
                ],
            }
        ]
    }
