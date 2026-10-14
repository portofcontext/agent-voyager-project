"""LangChain message data -> AVP wire shapes.

One chat-model call (one `AIMessage`) is one AVP turn. Only translation lives
here; ordering, spans, steps, tool pairing, and cost are the Recorder's job.
"""

from __future__ import annotations

import json
from typing import Any

from avp.content import (
    AVPContentBlock,
    Base64Source,
    Citation,
    ImageBlock,
    RefusalBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from avp.trajectory import ErrorCode, Usage


def content(message: Any) -> list[AVPContentBlock]:
    """An `AIMessage`'s output. Text and reasoning come from LangChain's
    provider-neutral `content_blocks`; tool calls come from `tool_calls` (and
    `invalid_tool_calls`, whose arguments failed to parse), keyed by the call
    id the `ToolMessage` echoes back."""
    blocks: list[AVPContentBlock] = []
    for block in message.content_blocks:
        kind = block.get("type")
        if kind == "text" and block.get("text"):
            blocks.append(
                TextBlock(text=block["text"], citations=_citations(block.get("annotations")))
            )
        elif kind == "reasoning":
            signature = (block.get("extras") or {}).get("signature")
            text = block.get("reasoning") or ""
            if text or signature:
                blocks.append(
                    ThinkingBlock(
                        thinking=text,
                        signature=signature,
                        redacted=True if not text else None,
                    )
                )
    if refusal := _refusal(message):
        blocks.append(RefusalBlock(refusal=refusal))
    for call in message.tool_calls:
        blocks.append(ToolUseBlock(id=call["id"], name=call["name"], input=call["args"]))
    for call in getattr(message, "invalid_tool_calls", None) or []:
        if call.get("id") and call.get("name"):
            blocks.append(
                ToolUseBlock(id=call["id"], name=call["name"], input={"_raw": call.get("args")})
            )
    return blocks


def _refusal(message: Any) -> str | None:
    if refusal := message.additional_kwargs.get("refusal"):
        return refusal
    if isinstance(message.content, list):
        for block in message.content:
            if isinstance(block, dict) and block.get("type") == "refusal":
                return block.get("refusal")
    return None


def is_refusal(message: Any) -> bool:
    return _refusal(message) is not None


def _citations(annotations: list[Any] | None) -> list[Citation] | None:
    cites = [a for a in annotations or [] if isinstance(a, dict) and a.get("type") == "citation"]
    if not cites:
        return None
    return [
        Citation(
            type="citation",
            cited_text=a.get("cited_text"),
            start_index=a.get("start_index"),
            end_index=a.get("end_index"),
            source_url=a.get("url"),
            source_title=a.get("title"),
        )
        for a in cites
    ]


def usage(metadata: dict[str, Any] | None) -> Usage | None:
    """LangChain `usage_metadata`. Its `input_tokens` already counts cache
    reads and writes (langchain-anthropic adds them back); cache writes are
    `cache_creation`, or split by TTL when Anthropic reports the split."""
    if not metadata:
        return None
    inp = metadata.get("input_token_details") or {}
    out = metadata.get("output_token_details") or {}
    written = inp.get("cache_creation") or (
        (inp.get("ephemeral_5m_input_tokens") or 0) + (inp.get("ephemeral_1h_input_tokens") or 0)
    )
    return Usage(
        input_tokens=metadata.get("input_tokens") or 0,
        output_tokens=metadata.get("output_tokens") or 0,
        cache_read_input_tokens=inp.get("cache_read") or None,
        cache_creation_input_tokens=written or None,
        reasoning_output_tokens=out.get("reasoning") or None,
    )


def response_model(message: Any) -> str | None:
    meta = message.response_metadata or {}
    return meta.get("model_name") or meta.get("model")


def finish_reasons(message: Any) -> list[str] | None:
    meta = message.response_metadata or {}
    reason = meta.get("finish_reason") or meta.get("stop_reason") or meta.get("status")
    return [reason] if reason else None


def tool_message(output: Any, call_id: str) -> Any | None:
    """The `ToolMessage` a tool produced: returned directly, or inside a
    LangGraph `Command` update (Deep Agents' `task` tool returns one)."""
    if getattr(output, "type", None) == "tool" and getattr(output, "tool_call_id", None):
        return output
    update = getattr(output, "update", None)
    if isinstance(update, dict):
        for message in update.get("messages") or []:
            if getattr(message, "tool_call_id", None) == call_id:
                return message
    return None


def tool_result(output: Any, call_id: str) -> tuple[str | list[Any], bool, dict[str, Any] | None]:
    """`(content, is_error, structured_content)` for one tool output."""
    message = tool_message(output, call_id)
    if message is None:
        return _text(output), False, None
    artifact = getattr(message, "artifact", None)
    structured = artifact.get("structured_content") if isinstance(artifact, dict) else None
    return (
        _result_content(message.content),
        getattr(message, "status", None) == "error",
        structured if isinstance(structured, dict) else None,
    )


def _result_content(raw: Any) -> str | list[Any]:
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, list):
        return _text(raw)
    blocks: list[Any] = []
    for block in raw:
        if isinstance(block, str):
            blocks.append(TextBlock(text=block))
        elif isinstance(block, dict) and block.get("type") == "text":
            blocks.append(TextBlock(text=block.get("text", "")))
        elif isinstance(block, dict) and block.get("type") == "image" and block.get("base64"):
            source = Base64Source(
                media_type=block.get("mime_type", "image/png"), data=block["base64"]
            )
            blocks.append(ImageBlock(source=source))
        else:
            blocks.append(TextBlock(text=_text(block)))
    return blocks


def result_text(output: str | list[Any]) -> str:
    if isinstance(output, str):
        return output
    return "\n".join(b.text for b in output if isinstance(b, TextBlock))


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def error_code(exc: BaseException) -> ErrorCode:
    """Provider errors by class name, so provider SDK imports stay lazy: the
    OpenAI and Anthropic SDKs share these names, and LangChain's own
    `Model*Error` taxonomy (which the Google integration raises) ends in them."""
    names = {c.__name__ for c in type(exc).__mro__}
    text = str(exc).lower()
    if names & _AUTH or _bad_key(names, text):
        return ErrorCode.auth_error
    if names & _RATE or _out_of_credits(exc, text):
        return ErrorCode.rate_limit
    if (
        "ContextOverflowError" in names
        or "context_length_exceeded" in text
        or "prompt is too long" in text
    ):
        return ErrorCode.context_limit
    return ErrorCode.agent_crash


_AUTH = {
    "AuthenticationError",
    "PermissionDeniedError",
    "ModelAuthenticationError",
    "ModelPermissionDeniedError",
}
_RATE = {"RateLimitError", "ModelRateLimitError"}


def _bad_key(names: set[str], text: str) -> bool:
    """Credentials missing or rejected without an auth error class: a client
    built without a key (the SDKs raise at construction or on the first
    request), and Google, which answers an invalid key with a 400
    `INVALID_ARGUMENT` whose reason is `API_KEY_INVALID`."""
    return (
        ("OpenAIError" in names and "api_key" in text)
        or "authentication method" in text
        or "api_key_invalid" in text
        or "api key not valid" in text
    )


def _out_of_credits(exc: BaseException, text: str) -> bool:
    """An exhausted balance or quota: OpenAI's `insufficient_quota` (which can
    also arrive mid-stream as a plain `APIError`) and Anthropic's low credit
    balance, which it reports as a 400."""
    return (
        getattr(exc, "code", None) == "insufficient_quota"
        or "insufficient_quota" in text
        or "no credits remaining" in text
        or "exceeded your current quota" in text
        or "credit balance is too low" in text
    )
