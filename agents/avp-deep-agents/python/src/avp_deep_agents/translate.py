"""LangChain's normalized messages and usage to AVP."""

import json

from avp.recorder import UsageReport
from avp.reports import ImageBlock, RefusalBlock, Source, TextBlock, ThinkingBlock, ToolUseBlock


def content(message):
    blocks = []
    for part in message.content_blocks:
        kind = part["type"]
        if kind == "text":
            blocks.append(TextBlock(type="text", text=part["text"], langchain=part))
        elif kind == "reasoning":
            blocks.append(
                ThinkingBlock(
                    type="thinking",
                    thinking=part.get("reasoning", ""),
                    signature=part.get("extras", {}).get("signature"),
                    langchain=part,
                )
            )
        elif kind in ("tool_call", "invalid_tool_call"):
            continue
        elif kind == "image" and part.get("base64"):
            blocks.append(
                ImageBlock(
                    type="image",
                    source=Source(type="base64", media_type=part["mime_type"], data=part["base64"]),
                )
            )
        elif kind == "non_standard" and (part.get("value") or {}).get("type") == "refusal":
            blocks.append(RefusalBlock(type="refusal", refusal=part["value"]["refusal"]))
        else:
            raise ValueError(f"unsupported LangChain content: {kind}")
    if refusal := message.additional_kwargs.get("refusal"):
        blocks.append(RefusalBlock(type="refusal", refusal=refusal))
    if message.invalid_tool_calls:
        raise ValueError("Deep Agents returned invalid tool arguments")
    for call in message.tool_calls:
        blocks.append(
            ToolUseBlock(type="tool_use", id=call["id"], name=call["name"], input=call["args"])
        )
    return blocks


def usage(native):
    if native is None:
        raise ValueError("Deep Agents response has no per-response usage")
    details = native.get("input_token_details", {})
    written = details.get("cache_creation") or details.get(
        "ephemeral_5m_input_tokens", 0
    ) + details.get("ephemeral_1h_input_tokens", 0)
    return UsageReport(
        input_tokens=native["input_tokens"],
        output_tokens=native["output_tokens"],
        cache_read_input_tokens=details.get("cache_read"),
        cache_creation_input_tokens=written or None,
        reasoning_output_tokens=native.get("output_token_details", {}).get("reasoning"),
    )


def tool_content(raw):
    if isinstance(raw, str):
        return raw
    blocks = []
    for part in raw:
        if isinstance(part, str):
            blocks.append(TextBlock(type="text", text=part))
        elif part["type"] == "text":
            blocks.append(TextBlock(type="text", text=part["text"]))
        elif part["type"] == "image" and part.get("base64"):
            blocks.append(
                ImageBlock(
                    type="image",
                    source=Source(type="base64", media_type=part["mime_type"], data=part["base64"]),
                )
            )
        else:
            blocks.append(TextBlock(type="text", text=json.dumps(part)))
    return blocks


def error_code(exc):
    names = {c.__name__ for c in type(exc).__mro__}
    text = str(exc).lower()
    if "StructuredOutputError" in names:
        return "output_invalid"
    if (
        names
        & {
            "AuthenticationError",
            "PermissionDeniedError",
            "ModelAuthenticationError",
            "ModelPermissionDeniedError",
        }
        or "api_key_invalid" in text
    ):
        return "auth_error"
    if (
        names & {"RateLimitError", "ModelRateLimitError"}
        or "insufficient_quota" in text
        or "no credits remaining" in text
    ):
        return "rate_limit"
    if (
        "context_length_exceeded" in text
        or "prompt is too long" in text
        or "ContextOverflowError" in names
    ):
        return "context_limit"
    return "agent_crash"
