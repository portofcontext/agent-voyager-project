"""What an agent sent the mock model. aimock's journal stores every provider's
request in one form: `messages` with roles, `tools` as OpenAI's function tools,
and `model`. Google's requests lose their tools' input schemas in that form."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelRequest:
    """One request in the mock model's journal, to the model API or `/mcp`."""

    path: str
    headers: dict[str, Any]
    body: dict[str, Any]


def _text(content: Any) -> str:
    """The text of a message's `content`: a string, or a list of text blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            _text(block.get("text", "")) for block in content if isinstance(block, dict)
        )
    return ""


def system_text(request: ModelRequest) -> str:
    """The system prompt."""
    messages = request.body.get("messages") or []
    return "\n".join(_text(m.get("content")) for m in messages if m.get("role") == "system").strip()


def model_id(request: ModelRequest) -> str | None:
    """The model asked for."""
    return request.body.get("model")


def offered_tools(request: ModelRequest) -> dict[str, tuple[str | None, Any]]:
    """Each tool offered to the model, by name, with its description and input
    schema, or None for a schema the journal doesn't have."""
    functions = [tool.get("function") or {} for tool in request.body.get("tools") or []]
    return {
        f["name"]: (f.get("description"), f.get("parameters")) for f in functions if "name" in f
    }


CREDENTIAL_HEADERS = {"authorization", "x-api-key", "api-key", "x-goog-api-key"}


def has_credential(request: ModelRequest) -> bool:
    """Whether the request has a model API key. aimock's journal redacts these
    headers, so only that one was sent can be seen, not its value."""
    return any(name.lower() in CREDENTIAL_HEADERS for name in request.headers)


def sent_value(request: ModelRequest, value: str) -> bool:
    """Whether a header holds `value`. Not for a header aimock's journal redacts."""
    return any(value in str(header) for header in request.headers.values())
