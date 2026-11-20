"""Pydantic AI messages -> ATIF objects.

One `ModelResponse` (one model call) is one agent step. Only translation lives
here; step order, result placement, and cost are the Recorder's job.
"""

import json
from collections.abc import Callable, Sequence
from typing import Any

from pydantic_ai import (
    FilePart,
    ModelHTTPError,
    ModelRequestPart,
    ModelResponse,
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

from avp.recorder import Call, Image, Part, Reasoning, ServerResult, Text, Usage
from avp.trajectory import Citation as AVPCitation
from avp.trajectory import ErrorCode

SaveImage = Callable[[bytes, str], Image]
"""Saves an image beside the Trajectory (`Recorder.image`)."""


def parts(response: ModelResponse, image: SaveImage) -> list[Part]:
    """A response's parts, in order. Tool calls the agent runs (output tools
    included) are calls; tools the model service runs are server-side calls
    with their results."""
    result: list[Part] = []
    for part in response.parts:
        if isinstance(part, TextPart):
            result.append(Text(text=part.content, citations=_citations(part.citations)))
        elif isinstance(part, ThinkingPart):
            if part.content:
                result.append(Reasoning(text=part.content, signature=part.signature))
            elif part.signature:
                # Anthropic's redacted thinking: the signature holds the encrypted block.
                result.append(Reasoning(encrypted_content=part.signature))
        elif isinstance(part, ToolCallPart):
            result.append(Call(id=part.tool_call_id, name=part.tool_name, arguments=_args(part)))
        elif isinstance(part, NativeToolCallPart):
            result.append(
                Call(
                    id=part.tool_call_id,
                    name=part.tool_name,
                    arguments=_args(part),
                    server_side=True,
                )
            )
        elif isinstance(part, NativeToolReturnPart):
            content = to_jsonable_python(part.content, fallback=str)
            result.append(
                ServerResult(
                    call_id=part.tool_call_id,
                    content=_text(content),
                    is_error=part.outcome != "success",
                    structured_content=None if isinstance(content, str) else content,
                )
            )
        elif isinstance(part, FilePart) and part.content.media_type.startswith("image/"):
            result.append(image(part.content.data, part.content.media_type))
        # Left out, because ATIF has no part for them:
        # - CompactionPart: the service's summary of earlier context.
        # - SpeechPart: audio the model spoke, with its transcript.
        # - FilePart that isn't an image, such as a generated PDF.
    return result


def _citations(citations: list[Citation] | None) -> list[AVPCitation] | None:
    """One citation per source of each Pydantic AI citation."""
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


def usage(native: RequestUsage) -> Usage | None:
    """One response's usage. Pydantic AI's `input_tokens` already includes
    cache reads and writes, as the Recorder's `prompt_tokens` does."""
    if not (native.input_tokens or native.output_tokens):
        return None
    return Usage(
        prompt_tokens=native.input_tokens,
        completion_tokens=native.output_tokens,
        cached_tokens=native.cache_read_tokens or None,
        cache_creation_input_tokens=native.cache_write_tokens or None,
        reasoning_output_tokens=native.output_reasoning_tokens or None,
    )


def finish_reasons(response: ModelResponse) -> list[str] | None:
    return [response.finish_reason] if response.finish_reason else None


def results(parts: Sequence[ModelRequestPart]) -> list[tuple[str, str, bool]]:
    """`(call_id, content, is_error)` for each tool result in a request. Any
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
