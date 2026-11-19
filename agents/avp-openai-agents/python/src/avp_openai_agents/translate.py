"""Responses items and native tool output to AVP content and usage."""

import json

from avp.recorder import Call, Reasoning, Text, Usage
from avp.trajectory import Citation


def _citation(annotation):
    named = {"url": "source_url", "title": "source_title", "file_id": "source_id"}
    raw = annotation.model_dump(mode="json", exclude_none=True)
    return Citation.model_validate({named.get(k, k): v for k, v in raw.items()})


def parts(items):
    blocks = []
    for item in items:
        if item.type == "message":
            for part in item.content:
                if part.type == "output_text":
                    citations = [_citation(a) for a in part.annotations]
                    blocks.append(Text(text=part.text, citations=citations or None))
                elif part.type == "refusal":
                    blocks.append(Text(refusal=True, text=part.refusal))
                else:
                    raise ValueError(f"unsupported OpenAI content: {part.type}")
        elif item.type == "function_call":
            arguments = json.loads(item.arguments)
            blocks.append(Call(id=item.call_id, name=item.name, arguments=arguments))
        elif item.type == "reasoning":
            blocks.append(
                Reasoning(
                    text="\n".join(p.text for p in item.summary or []),
                    encrypted_content=item.encrypted_content,
                )
            )
        else:
            raise ValueError(f"unsupported OpenAI response item: {item.type}")
    return blocks


def usage(native):
    if native is None:
        raise ValueError("OpenAI response has no per-response usage")
    return Usage(
        prompt_tokens=native.input_tokens,
        completion_tokens=native.output_tokens,
        cached_tokens=getattr(native.input_tokens_details, "cached_tokens", None),
        cache_creation_input_tokens=getattr(
            native.input_tokens_details, "cache_write_tokens", None
        ),
        reasoning_output_tokens=getattr(native.output_tokens_details, "reasoning_tokens", None),
    )


def tool_output(raw, rec):
    if isinstance(raw, str):
        return raw
    blocks = []
    for part in raw:
        if part["type"] in ("text", "input_text"):
            blocks.append(Text(text=part["text"]))
        elif part["type"] == "input_image" and part["image_url"].startswith("data:"):
            header, data = part["image_url"].split(",", 1)
            blocks.append(rec.image_base64(data, header.removeprefix("data:").split(";")[0]))
        else:
            blocks.append(Text(text=json.dumps(part)))
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
