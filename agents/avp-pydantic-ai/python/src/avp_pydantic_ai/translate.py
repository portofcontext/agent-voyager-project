"""Pydantic AI messages -> AVP wire shapes.

One `ModelResponse` (one model call) is one AVP turn. Only translation lives
here; ordering, spans, steps, tool pairing, and cost are the Recorder's job.
"""

from __future__ import annotations

import json
from typing import Any

from avp.content import AVPContentBlock, TextBlock, ThinkingBlock, ToolUseBlock
from avp.trajectory import ErrorCode, Usage


def content(parts: list[Any]) -> list[AVPContentBlock]:
    """A response's parts. Tool calls (output tools included) become
    `tool_use` blocks keyed by `tool_call_id`."""
    from pydantic_ai import TextPart, ThinkingPart, ToolCallPart

    blocks: list[AVPContentBlock] = []
    for part in parts:
        if isinstance(part, TextPart):
            blocks.append(TextBlock(text=part.content))
        elif isinstance(part, ToolCallPart):
            blocks.append(
                ToolUseBlock(id=part.tool_call_id, name=part.tool_name, input=_args(part))
            )
        elif isinstance(part, ThinkingPart):
            blocks.append(
                ThinkingBlock(
                    thinking=part.content,
                    signature=part.signature,
                    redacted=True if not part.content and part.signature else None,
                )
            )
    return blocks


def _args(part: Any) -> dict[str, Any]:
    try:
        return part.args_as_dict()
    except (ValueError, AssertionError):
        return {"_raw": part.args}


def usage(native: Any) -> Usage | None:
    """Per-request usage. Pydantic AI's `input_tokens` already includes cache
    reads and writes, as AVP's does."""
    if native is None or not (native.input_tokens or native.output_tokens):
        return None
    return Usage(
        input_tokens=native.input_tokens,
        output_tokens=native.output_tokens,
        cache_read_input_tokens=native.cache_read_tokens or None,
        cache_creation_input_tokens=native.cache_write_tokens or None,
        reasoning_output_tokens=native.output_reasoning_tokens or None,
    )


def finish_reasons(response: Any) -> list[str] | None:
    return [response.finish_reason] if response.finish_reason else None


def tool_results(parts: list[Any]) -> list[tuple[str, str, bool]]:
    """`(call_id, output, is_error)` for each tool result in a request: a
    return (a `failed` outcome is an error) or a retry prompt answering a call."""
    from pydantic_ai import RetryPromptPart, ToolReturnPart

    results = []
    for part in parts:
        if isinstance(part, ToolReturnPart):
            failed = part.outcome not in (None, "success")
            results.append((part.tool_call_id, _text(part.content), failed))
        elif isinstance(part, RetryPromptPart) and part.tool_name is not None:
            results.append((part.tool_call_id, _text(part.content), True))
    return results


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return "\n".join(value)
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def error_code(exc: BaseException) -> ErrorCode:
    """Provider errors by status and message, so the provider SDKs stay lazy."""
    from pydantic_ai import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded, UserError

    text = str(exc).lower()
    if isinstance(exc, ModelHTTPError):
        if exc.status_code in (401, 403):
            return ErrorCode.auth_error
        if exc.status_code == 429 or _out_of_credits(text):
            return ErrorCode.rate_limit
        if ("context" in text and ("length" in text or "window" in text)) or "too long" in text:
            return ErrorCode.context_limit
    if isinstance(exc, UserError) and "api_key" in text.replace(" ", "_"):
        return ErrorCode.auth_error
    if isinstance(exc, (UnexpectedModelBehavior, UsageLimitExceeded)):
        return ErrorCode.unknown
    return ErrorCode.agent_crash


def _out_of_credits(text: str) -> bool:
    return (
        "insufficient_quota" in text
        or "credit balance is too low" in text
        or "exceeded your current quota" in text
    )
