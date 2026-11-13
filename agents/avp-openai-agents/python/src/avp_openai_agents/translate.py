"""Responses items and native tool output to AVP content and usage."""

import json

from avp.recorder import UsageReport
from avp.reports import ImageBlock, RefusalBlock, Source, TextBlock, ThinkingBlock, ToolUseBlock


def content(items):
    blocks = []
    for item in items:
        if item.type == "message":
            for part in item.content:
                if part.type == "output_text":
                    blocks.append(
                        TextBlock(
                            type="text",
                            text=part.text,
                            openai=part.model_dump(mode="json", exclude_none=True),
                        )
                    )
                elif part.type == "refusal":
                    blocks.append(RefusalBlock(type="refusal", refusal=part.refusal))
                else:
                    raise ValueError(f"unsupported OpenAI content: {part.type}")
        elif item.type == "function_call":
            arguments = json.loads(item.arguments)
            blocks.append(
                ToolUseBlock(type="tool_use", id=item.call_id, name=item.name, input=arguments)
            )
        elif item.type == "reasoning":
            blocks.append(
                ThinkingBlock(
                    type="thinking",
                    thinking="\n".join(p.text for p in item.summary or []),
                    signature=item.encrypted_content,
                    openai=item.model_dump(mode="json", exclude_none=True),
                )
            )
        else:
            raise ValueError(f"unsupported OpenAI response item: {item.type}")
    return blocks


def usage(native):
    if native is None:
        raise ValueError("OpenAI response has no per-response usage")
    return UsageReport(
        input_tokens=native.input_tokens,
        output_tokens=native.output_tokens,
        cache_read_input_tokens=getattr(native.input_tokens_details, "cached_tokens", None),
        cache_creation_input_tokens=getattr(
            native.input_tokens_details, "cache_write_tokens", None
        ),
        reasoning_output_tokens=getattr(native.output_tokens_details, "reasoning_tokens", None),
    )


def tool_output(raw):
    if isinstance(raw, str):
        return raw
    blocks = []
    for part in raw:
        if part["type"] in ("text", "input_text"):
            blocks.append(TextBlock(type="text", text=part["text"]))
        elif part["type"] == "input_image" and part["image_url"].startswith("data:"):
            header, data = part["image_url"].split(",", 1)
            blocks.append(
                ImageBlock(
                    type="image",
                    source=Source(
                        type="base64",
                        media_type=header.removeprefix("data:").split(";")[0],
                        data=data,
                    ),
                )
            )
        else:
            blocks.append(TextBlock(type="text", text=json.dumps(part)))
    return blocks


def error_code(exc):
    names = {c.__name__ for c in type(exc).__mro__}
    if names & {"AuthenticationError", "PermissionDeniedError"}:
        return "auth_error"
    text = str(exc).lower()
    if (
        "RateLimitError" in names
        or "insufficient_quota" in text
        or "no credits remaining" in text
        or "exceeded your current quota" in text
    ):
        return "rate_limit"
    if "context_length_exceeded" in text or "ContextWindowExceededError" in names:
        return "context_limit"
    return "agent_crash"
