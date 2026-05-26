"""avp.content — AVP content block types for assistant message content.

Normalized content union covering the message-history shapes of Anthropic
Messages, OpenAI Chat Completions + Responses, Google Gemini
generateContent, AWS Bedrock Converse, Cohere Chat, and Mistral Chat.
The goal is non-lossy round-trip of agent history across providers.

Every block sets `model_config = ConfigDict(extra="allow")` so unmodeled
provider-specific fields (Anthropic `cache_control`, OpenAI
`encrypted_content`, Gemini `thought_signature`, future additions)
round-trip unchanged without spec churn.

Discriminate on the `type` field. Serialize with
`model_dump(by_alias=True, mode="json")`.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from avp.envelope import _OPEN

# ── Source variants ───────────────────────────────────────────────────────────


class Base64Source(BaseModel):
    """Inline base64-encoded media. Anthropic `source.type=base64`, Gemini
    `inline_data`, Bedrock `source.bytes`."""

    model_config = _OPEN
    type: Literal["base64"] = "base64"
    media_type: str
    data: str


class UrlSource(BaseModel):
    """External URL. Anthropic `source.type=url`, OpenAI `image_url`,
    Gemini `file_data` (when `file_uri` is a public URL)."""

    model_config = _OPEN
    type: Literal["url"] = "url"
    url: str


class FileSource(BaseModel):
    """Provider-hosted file reference. OpenAI Files API `file_id`, Anthropic
    Files API `file_id`, Gemini `file_data.file_uri` (Files API URI)."""

    model_config = _OPEN
    type: Literal["file"] = "file"
    file_id: str


Source = Annotated[Base64Source | UrlSource | FileSource, Field(discriminator="type")]


# ── Citations / annotations ───────────────────────────────────────────────────


class Citation(BaseModel):
    """Span-anchored attribution on a text or document block. Unifies
    Anthropic citations (`char_location`, `page_location`,
    `content_block_location`), OpenAI annotations (`url_citation`,
    `file_citation`, `file_path`), and Gemini grounding chunks. `type`
    carries the provider's raw citation kind verbatim so downstream
    consumers can normalize without re-deriving it."""

    model_config = _OPEN
    type: str
    cited_text: str | None = None
    start_index: int | None = Field(default=None, ge=0)
    end_index: int | None = Field(default=None, ge=0)
    source_id: str | None = None
    source_url: str | None = None
    source_title: str | None = None


# ── Blocks ────────────────────────────────────────────────────────────────────


class TextBlock(BaseModel):
    """Plain text content. Anthropic `text`, OpenAI `text` /
    `output_text` / `input_text`, Gemini text part, Bedrock `text`,
    Cohere `text`, Mistral `text`. `citations` carries Anthropic citations,
    OpenAI annotations, and Gemini grounding spans anchored into this text."""

    model_config = _OPEN
    type: Literal["text"] = "text"
    text: str
    citations: list[Citation] | None = None


class ThinkingBlock(BaseModel):
    """Reasoning / chain-of-thought emitted by the model.

    Anthropic extended thinking, OpenAI o-series `reasoning` items,
    Gemini `thought` parts, Bedrock `reasoningContent`, Mistral thinking.
    `signature` is the opaque blob the provider requires echoed back on
    the next turn for continued reasoning: Anthropic's cryptographic
    signature, OpenAI's `encrypted_content`, or Gemini's
    `thought_signature`. `redacted` flags blocks whose plaintext is
    unavailable (encrypted-only form)."""

    model_config = _OPEN
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: str | None = None
    redacted: bool | None = None


class ImageBlock(BaseModel):
    """Image content. Anthropic `image`, OpenAI `image_url` /
    `input_image`, Gemini `inline_data` / `file_data` image, Bedrock
    `image`."""

    model_config = _OPEN
    type: Literal["image"] = "image"
    source: Source


class AudioBlock(BaseModel):
    """Audio content. OpenAI `input_audio` (input) and `audio` (output),
    Gemini `inline_data` audio, Bedrock `audio`. `transcript` carries
    OpenAI's output-audio transcript when present."""

    model_config = _OPEN
    type: Literal["audio"] = "audio"
    source: Source
    transcript: str | None = None


class VideoBlock(BaseModel):
    """Video content. Gemini `inline_data` / `file_data` video, Bedrock
    `video`."""

    model_config = _OPEN
    type: Literal["video"] = "video"
    source: Source


class DocumentBlock(BaseModel):
    """Document / file content (typically PDFs). Anthropic `document`
    (with citation support), OpenAI `input_file`, Gemini `file_data`,
    Bedrock `document`. `title` is the document name used as the
    citation target; `context` is supplementary metadata Anthropic
    surfaces alongside the document for the model."""

    model_config = _OPEN
    type: Literal["document"] = "document"
    source: Source
    title: str | None = None
    context: str | None = None
    citations: list[Citation] | None = None


class ToolUseBlock(BaseModel):
    """Model invokes a client-dispatched tool. Anthropic `tool_use`,
    OpenAI `function_call` / `tool_calls`, Gemini `function_call`,
    Bedrock `toolUse`, Cohere tool_calls, Mistral tool_calls."""

    model_config = _OPEN
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


ToolResultContent = Annotated[TextBlock | ImageBlock | DocumentBlock, Field(discriminator="type")]


class ToolResultBlock(BaseModel):
    """Result of a client-dispatched tool call. Anthropic `tool_result`,
    OpenAI `function_call_output` / tool-role message, Gemini
    `function_response`, Bedrock `toolResult`. Anthropic permits nested
    text/image/document content blocks; other providers serialize a
    flat string. `structured_content` carries a programmatic payload
    alongside the human-readable `content` (MCP's `structuredContent`,
    Gemini `function_response.response`, Bedrock `toolResult.content.json`);
    the two channels are complementary, not alternatives. `is_error`
    flags rejections."""

    model_config = _OPEN
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[ToolResultContent]
    structured_content: dict[str, Any] | None = None
    is_error: bool | None = None


class ServerToolUseBlock(BaseModel):
    """Built-in tool executed by the provider rather than the agent.
    Anthropic `server_tool_use` (web_search, code_execution), OpenAI
    Responses `web_search_call` / `file_search_call` / `computer_call` /
    `code_interpreter_call`, Gemini `executable_code` / `google_search`.
    `name` carries the tool kind (e.g. "web_search", "code_interpreter",
    "computer_use", "google_search"). Distinct from `tool_use` because
    the agent never dispatches these; they are observability of a
    provider-side action."""

    model_config = _OPEN
    type: Literal["server_tool_use"] = "server_tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ServerToolResultBlock(BaseModel):
    """Result of a provider-executed built-in tool. Pairs with
    `ServerToolUseBlock`. Anthropic `web_search_tool_result`, OpenAI
    Responses `*_call_output`, Gemini `code_execution_result`.
    `content` is provider-shaped (search-result rows, code stdout,
    computer-use screenshots, ...)."""

    model_config = _OPEN
    type: Literal["server_tool_result"] = "server_tool_result"
    tool_use_id: str
    name: str
    content: Any
    is_error: bool | None = None


class RefusalBlock(BaseModel):
    """Structured refusal distinct from generated text. OpenAI assistant
    message `refusal` field and Responses `output_refusal` item. Other
    providers emit refusals as plain text plus a finish reason; this
    block represents only providers that ship a typed refusal."""

    model_config = _OPEN
    type: Literal["refusal"] = "refusal"
    refusal: str


# ── Discriminated union ───────────────────────────────────────────────────────


AVPContentBlock = Annotated[
    TextBlock
    | ThinkingBlock
    | ImageBlock
    | AudioBlock
    | VideoBlock
    | DocumentBlock
    | ToolUseBlock
    | ToolResultBlock
    | ServerToolUseBlock
    | ServerToolResultBlock
    | RefusalBlock,
    Field(discriminator="type"),
]


__all__ = [
    "AVPContentBlock",
    "AudioBlock",
    "Base64Source",
    "Citation",
    "DocumentBlock",
    "FileSource",
    "ImageBlock",
    "RefusalBlock",
    "ServerToolResultBlock",
    "ServerToolUseBlock",
    "Source",
    "TextBlock",
    "ThinkingBlock",
    "ToolResultBlock",
    "ToolResultContent",
    "ToolUseBlock",
    "UrlSource",
    "VideoBlock",
]
