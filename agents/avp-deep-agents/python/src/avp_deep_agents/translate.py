"""LangChain's normalized messages and usage to AVP."""

import json

from avp.recorder import Call, Reasoning, Text, Usage
from avp.trajectory import Citation


def _citation(raw):
    named = {"url": "source_url", "title": "source_title"}
    return Citation.model_validate({named.get(k, k): v for k, v in raw.items()})


def parts(message, rec):
    blocks = []
    for part in message.content_blocks:
        kind = part["type"]
        if kind == "text":
            citations = [_citation(a) for a in part.get("annotations", [])]
            blocks.append(Text(text=part["text"], citations=citations or None))
        elif kind == "reasoning":
            blocks.append(
                Reasoning(
                    text=part.get("reasoning", ""),
                    signature=part.get("extras", {}).get("signature"),
                )
            )
        elif kind in ("tool_call", "invalid_tool_call"):
            continue
        elif kind == "image" and part.get("base64"):
            blocks.append(rec.image_base64(part["base64"], part["mime_type"]))
        elif kind == "non_standard" and (part.get("value") or {}).get("type") == "refusal":
            blocks.append(Text(refusal=True, text=part["value"]["refusal"]))
        else:
            raise ValueError(f"unsupported LangChain content: {kind}")
    if refusal := message.additional_kwargs.get("refusal"):
        blocks.append(Text(refusal=True, text=refusal))
    if message.invalid_tool_calls:
        raise ValueError("Deep Agents returned invalid tool arguments")
    for call in message.tool_calls:
        blocks.append(Call(id=call["id"], name=call["name"], arguments=call["args"]))
    return blocks


def usage(native):
    if native is None:
        raise ValueError("Deep Agents response has no per-response usage")
    details = native.get("input_token_details", {})
    written = details.get("cache_creation") or details.get(
        "ephemeral_5m_input_tokens", 0
    ) + details.get("ephemeral_1h_input_tokens", 0)
    return Usage(
        prompt_tokens=native["input_tokens"],
        completion_tokens=native["output_tokens"],
        cached_tokens=details.get("cache_read"),
        cache_creation_input_tokens=written or None,
        reasoning_output_tokens=native.get("output_token_details", {}).get("reasoning"),
    )


def tool_content(raw, rec):
    if isinstance(raw, str):
        return raw
    blocks = []
    for part in raw:
        if isinstance(part, str):
            blocks.append(Text(text=part))
        elif part["type"] == "text":
            blocks.append(Text(text=part["text"]))
        elif part["type"] == "image" and part.get("base64"):
            blocks.append(rec.image_base64(part["base64"], part["mime_type"]))
        else:
            blocks.append(Text(text=json.dumps(part)))
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
