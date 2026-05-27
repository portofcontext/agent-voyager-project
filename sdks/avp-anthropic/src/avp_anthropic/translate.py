"""Translation DTOs for the AVP ↔ Anthropic boundary.

These are avp-anthropic's own per-turn translation output types, not a
shared protocol. `AnthropicModelDriver.step` returns a `ModelResponse`;
an agent loop (the reference agent, a traced client) reads it and emits
the corresponding `avp.trajectory` events directly to an `EventSink`.

The old `avp.agent.drivers` `ModelDriver` / `ToolDriver` Protocols are
gone (the binding is wire-types-only); the loop is inlined by each
integrator, so only the data shapes live on. `ToolOutcome` is kept here
for the reference agent's local tool catalog to return.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from avp.content import (
    AVPContentBlock,
    RefusalBlock,
    ServerToolResultBlock,
    ServerToolUseBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from avp.trajectory import ErrorCode, Usage


@dataclass
class ScriptedToolCall:
    """A tool USE the model requested this turn; the agent dispatches it."""

    call_id: str
    tool: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class Refusal:
    """The model declined this turn via a provider refusal signal.

    `reason` carries the provider's verbatim stop-reason code; `message`
    is the refusal text when the model produced one; `category` is the
    provider's safety classification when given; `provider` lets
    downstreams normalize across providers. A refusal terminates the turn
    (the loop stops with `StopReason.refused`).
    """

    reason: str
    message: str | None = None
    category: str | None = None
    provider: str | None = None


@dataclass
class ReasoningBlock:
    """A reasoning / thinking block the model produced this turn.

    Populated from provider shapes (Anthropic `thinking` /
    `redacted_thinking` blocks). `text` is the visible chain-of-thought
    (empty when redacted); `signature` carries the provider's signature
    when returned; `redacted` is True when the block came back
    encrypted-only.
    """

    text: str = ""
    signature: str | None = None
    redacted: bool = False


@dataclass
class ServerToolCall:
    """A tool call the API/SDK ran server-side during this turn.

    Distinct from `ScriptedToolCall`: a `ServerToolCall` already happened
    (the API ran the tool inline and returned the result in the same
    response: Anthropic `mcp_tool_use`/`mcp_tool_result`, `web_search`,
    code execution). The loop emits synthetic `tool_invoked` /
    `tool_returned` events for per-call fidelity, parented to the turn
    span. No agent dispatch happens.
    """

    call_id: str
    tool: str
    input: dict[str, Any]
    output_text: str = ""
    output_structured: Any | None = None
    is_error: bool = False
    duration_ms: int = 0
    dispatch_target: Literal["mcp_server", "local"] = "mcp_server"
    server_id: str | None = None


@dataclass
class ModelResponse:
    """One translated model turn. `AnthropicModelDriver.step` returns this;
    the loop turns it into `assistant_message` (+ any tool events)."""

    tokens_input: int
    tokens_output: int
    cost_usd: float
    duration_ms: int
    text: str | None = None
    tool_calls: list[ScriptedToolCall] = field(default_factory=list)
    server_tool_calls: list[ServerToolCall] = field(default_factory=list)
    reasoning_blocks: list[ReasoningBlock] = field(default_factory=list)
    refusal: Refusal | None = None
    tokens_cache_read: int | None = None
    tokens_cache_write: int | None = None
    tokens_reasoning_output: int | None = None
    converged: bool = False
    # Provenance for the cost number — `computed` (math done locally),
    # `reported` (API/SDK gave the number), or `unknown` (no price found).
    # Tagged on assistant_message as `avp.cost.source`.
    cost_source: str = "computed"
    # Streaming observability (OTel GenAI conventions). Populated when the
    # underlying call streamed; non-streaming leaves them None.
    streamed: bool | None = None
    time_to_first_chunk_s: float | None = None
    response_model: str | None = None
    finish_reasons: list[str] | None = None


class ModelDriverError(Exception):
    """Raised by `AnthropicModelDriver.step()` when a provider call fails.

    Carries an `ErrorCode` hint so the loop can emit
    `error_occurred(code=...)` with the right classification instead of
    `unknown`. Untyped exceptions propagating past `step()` are treated by
    the loop as `agent_crash`.
    """

    def __init__(self, message: str, *, code: ErrorCode) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ToolOutcome:
    """Result of a local tool dispatch, returned by the reference agent's
    `ShellTools`-style catalog. The loop renders it into `tool_returned`."""

    output: str | None = None
    output_json: Any | None = None
    error: str | None = None
    duration_ms: int = 1
    rejected: bool = False
    rejection_reason: str | None = None


# ── ModelResponse → AVP wire converters ───────────────────────────────────────
#
# Shared by every loop that turns a translated turn into the wire: the
# reference agent and the traced client both call these so an
# `assistant_message` carries identical content / usage regardless of which
# loop produced it. The single Anthropic→ModelResponse walker lives in
# `driver._anthropic_response_to_avp`; these are the ModelResponse→event half.


def model_response_usage(mr: ModelResponse) -> Usage:
    """Project a `ModelResponse`'s token counts onto `avp.usage`.

    `input_tokens` already INCLUDES cache reads (AVP convention; the driver
    adds them back); the cache breakdowns ride along informationally.
    """
    return Usage(
        input_tokens=mr.tokens_input,
        output_tokens=mr.tokens_output,
        cache_read_input_tokens=mr.tokens_cache_read,
        cache_creation_input_tokens=mr.tokens_cache_write,
        reasoning_output_tokens=mr.tokens_reasoning_output,
    )


def model_response_to_content(mr: ModelResponse) -> list[AVPContentBlock]:
    """Render a `ModelResponse` as the `avp.content` block list for an
    `assistant_message`.

    Order: thinking, then text, then a refusal (if any), then the model's
    tool_use blocks, then each server-side tool use paired with its result.
    Server tool calls already ran inside the API response, so both the use
    and the result block surface here.
    """
    blocks: list[AVPContentBlock] = []
    for rb in mr.reasoning_blocks:
        blocks.append(
            ThinkingBlock(thinking=rb.text, signature=rb.signature, redacted=rb.redacted or None)
        )
    if mr.text:
        blocks.append(TextBlock(text=mr.text))
    if mr.refusal is not None:
        blocks.append(RefusalBlock(refusal=mr.refusal.message or mr.refusal.reason))
    for tc in mr.tool_calls:
        blocks.append(ToolUseBlock(id=tc.call_id, name=tc.tool, input=tc.input))
    for st in mr.server_tool_calls:
        blocks.append(ServerToolUseBlock(id=st.call_id, name=st.tool, input=st.input))
        blocks.append(
            ServerToolResultBlock(
                tool_use_id=st.call_id,
                name=st.tool,
                content=(
                    st.output_structured if st.output_structured is not None else st.output_text
                ),
                is_error=st.is_error or None,
            )
        )
    return blocks
