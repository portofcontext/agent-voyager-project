"""OpenAI Responses API data -> AVP wire shapes.

One `Response` (one model call) is one AVP turn. Only translation lives here;
ordering, spans, steps, tool pairing, and cost are the Recorder's job.
"""

from __future__ import annotations

import json
from typing import Any

from avp.content import (
    AVPContentBlock,
    Citation,
    RefusalBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from avp.trajectory import ErrorCode, Usage


def content(output: list[Any]) -> list[AVPContentBlock]:
    """A response's output items. Function calls become `tool_use` blocks
    keyed by `call_id` (what the tool output item echoes back)."""
    blocks: list[AVPContentBlock] = []
    for item in output:
        kind = getattr(item, "type", None)
        if kind == "message":
            for part in item.content:
                if part.type == "output_text":
                    blocks.append(TextBlock(text=part.text, citations=_citations(part.annotations)))
                elif part.type == "refusal":
                    blocks.append(RefusalBlock(refusal=part.refusal))
        elif kind == "function_call":
            blocks.append(ToolUseBlock(id=item.call_id, name=item.name, input=_args(item)))
        elif kind == "reasoning":
            parts = item.summary or item.content or []
            text = "\n\n".join(p.text for p in parts)
            blocks.append(
                ThinkingBlock(
                    thinking=text,
                    signature=item.encrypted_content,
                    redacted=True if not text and item.encrypted_content else None,
                )
            )
    return blocks


def _citations(annotations: list[Any] | None) -> list[Citation] | None:
    if not annotations:
        return None
    return [
        Citation(
            type=a.type,
            start_index=getattr(a, "start_index", None),
            end_index=getattr(a, "end_index", None),
            source_id=getattr(a, "file_id", None),
            source_url=getattr(a, "url", None),
            source_title=getattr(a, "title", None),
        )
        for a in annotations
    ]


def _args(call: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        return {"_raw": call.arguments}
    return parsed if isinstance(parsed, dict) else {"_value": parsed}


def usage(native: Any) -> Usage | None:
    """Responses usage: `input_tokens` already includes cache reads and writes."""
    if native is None:
        return None
    cached = getattr(native.input_tokens_details, "cached_tokens", None)
    written = getattr(native.input_tokens_details, "cache_write_tokens", None)
    reasoning = getattr(native.output_tokens_details, "reasoning_tokens", None)
    return Usage(
        input_tokens=native.input_tokens,
        output_tokens=native.output_tokens,
        cache_read_input_tokens=cached or None,
        cache_creation_input_tokens=written or None,
        reasoning_output_tokens=reasoning or None,
    )


def finish_reasons(response: Any) -> list[str] | None:
    details = getattr(response, "incomplete_details", None)
    if details is not None and details.reason:
        return [details.reason]
    return [response.status] if response.status else None


def tool_output(item: Any) -> str:
    """The tool result as sent back to the model."""
    raw = item.raw_item
    out = raw.get("output") if isinstance(raw, dict) else getattr(raw, "output", None)
    if out is None:
        out = item.output
    return out if isinstance(out, str) else json.dumps(out, default=str)


def call_id(item: Any) -> str | None:
    raw = item.raw_item
    return raw.get("call_id") if isinstance(raw, dict) else getattr(raw, "call_id", None)


def error_code(exc: BaseException) -> ErrorCode:
    """Provider errors by class name, so the `openai` import stays lazy."""
    names = {c.__name__ for c in type(exc).__mro__}
    if "AuthenticationError" in names or "PermissionDeniedError" in names:
        return ErrorCode.auth_error
    if "RateLimitError" in names:
        return ErrorCode.rate_limit
    if "context_length_exceeded" in str(exc) or "ContextWindowExceededError" in names:
        return ErrorCode.context_limit
    if "MaxTurnsExceeded" in names:
        return ErrorCode.unknown
    return ErrorCode.agent_crash
