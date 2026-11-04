"""Pydantic AI messages -> AVP shapes.

One `ModelResponse` (one model call) is one AVP response. Only translation
lives here; event order, tool pairing, and cost are the Recorder's job.
"""

import base64
import json
from collections.abc import Sequence
from typing import Any

from pydantic_ai import (
    FilePart,
    ModelHTTPError,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    NativeToolCallPart,
    NativeToolReturnPart,
    RequestUsage,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UserError,
)
from pydantic_ai.messages import (
    BaseToolCallPart,
    Citation,
    ContentCitationAnchor,
    DocumentCitationSource,
    WebCitationSource,
)
from pydantic_core import to_jsonable_python

from avp.recorder import UsageReport
from avp.trajectory import Citation as AVPCitation
from avp.trajectory import (
    ContentBlock,
    ErrorCode,
    ImageBlock,
    ServerToolResultBlock,
    ServerToolUseBlock,
    Source,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)


def content(parts: Sequence[ModelResponsePart]) -> list[ContentBlock]:
    """A response's parts as content blocks. Tool calls the agent runs (output
    tools included) become `tool_use` blocks; tools the model service runs
    become `server_tool_use` and `server_tool_result`."""
    blocks: list[ContentBlock] = []
    for part in parts:
        if isinstance(part, TextPart):
            blocks.append(
                TextBlock(type="text", text=part.content, citations=_citations(part.citations))
            )
        elif isinstance(part, ThinkingPart):
            blocks.append(
                ThinkingBlock(
                    type="thinking",
                    thinking=part.content,
                    signature=part.signature,
                    redacted=True if not part.content and part.signature else None,
                )
            )
        elif isinstance(part, ToolCallPart):
            blocks.append(
                ToolUseBlock(
                    type="tool_use", id=part.tool_call_id, name=part.tool_name, input=_args(part)
                )
            )
        elif isinstance(part, NativeToolCallPart):
            blocks.append(
                ServerToolUseBlock(
                    type="server_tool_use",
                    id=part.tool_call_id,
                    name=part.tool_name,
                    input=_args(part),
                )
            )
        elif isinstance(part, NativeToolReturnPart):
            blocks.append(
                ServerToolResultBlock(
                    type="server_tool_result",
                    tool_use_id=part.tool_call_id,
                    name=part.tool_name,
                    content=to_jsonable_python(part.content, fallback=str),
                    is_error=True if part.outcome != "success" else None,
                )
            )
        elif isinstance(part, FilePart) and part.content.media_type.startswith("image/"):
            source = Source(
                type="base64",
                media_type=part.content.media_type,
                data=base64.b64encode(part.content.data).decode(),
            )
            blocks.append(ImageBlock(type="image", source=source))
        # Left out, because AVP has no block for them:
        # - CompactionPart: the service's summary of earlier context.
        # - SpeechPart: audio the model spoke, with its transcript.
        # - FilePart that isn't an image, such as a generated PDF.
    return blocks


def _citations(citations: list[Citation] | None) -> list[AVPCitation] | None:
    """One AVP citation per source of each Pydantic AI citation."""
    result = []
    for citation in citations or []:
        anchor = citation.anchor if isinstance(citation.anchor, ContentCitationAnchor) else None
        for source in citation.sources:
            result.append(
                AVPCitation(
                    type=source.kind,
                    cited_text=source.excerpts[0] if source.excerpts else None,
                    start_index=anchor.start if anchor else None,
                    end_index=anchor.end if anchor else None,
                    source_id=source.document_id
                    if isinstance(source, DocumentCitationSource)
                    else None,
                    source_url=source.url if isinstance(source, WebCitationSource) else None,
                    source_title=source.title,
                )
            )
    return result or None


def _args(part: BaseToolCallPart) -> dict[str, Any]:
    try:
        return part.args_as_dict()
    except (ValueError, AssertionError):
        return {"_raw": part.args}


def usage(native: RequestUsage) -> UsageReport | None:
    """One response's usage. Pydantic AI's `input_tokens` already includes
    cache reads and writes, as AVP's does."""
    if not (native.input_tokens or native.output_tokens):
        return None
    return UsageReport(
        input_tokens=native.input_tokens,
        output_tokens=native.output_tokens,
        cache_read_input_tokens=native.cache_read_tokens or None,
        cache_creation_input_tokens=native.cache_write_tokens or None,
        reasoning_output_tokens=native.output_reasoning_tokens or None,
    )


def finish_reasons(response: ModelResponse) -> list[str] | None:
    return [response.finish_reason] if response.finish_reason else None


def tool_results(parts: Sequence[ModelRequestPart]) -> list[tuple[str, str, bool]]:
    """`(call_id, output, is_error)` for each tool result in a request. Any
    outcome but `success`, such as `failed` or `retried`, is an error."""
    return [
        (part.tool_call_id, _text(part.content), part.outcome not in (None, "success"))
        for part in parts
        if isinstance(part, ToolReturnPart)
    ]


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return "\n".join(value)
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def error_code(exc: Exception) -> ErrorCode:
    """Provider errors by status and message, so the provider SDKs stay lazy."""
    text = str(exc).lower()
    if isinstance(exc, ModelHTTPError):
        if exc.status_code in (401, 403):
            return "auth_error"
        if exc.status_code == 429 or _out_of_credits(text):
            return "rate_limit"
        if ("context" in text and ("length" in text or "window" in text)) or "too long" in text:
            return "context_limit"
    if isinstance(exc, UserError) and "api_key" in text.replace(" ", "_"):
        return "auth_error"
    if isinstance(exc, UnexpectedModelBehavior) and "output retries" in text:
        return "output_invalid"
    if isinstance(exc, (UnexpectedModelBehavior, UsageLimitExceeded)):
        return "unknown"
    return "agent_crash"


def _out_of_credits(text: str) -> bool:
    return (
        "insufficient_quota" in text
        or "credit balance is too low" in text
        or "exceeded your current quota" in text
    )
