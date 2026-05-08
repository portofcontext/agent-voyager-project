"""AnthropicModelDriver — implements avp.agent.ModelDriver against the Anthropic SDK.

Each call to .step(history) translates AVP history → Anthropic messages, invokes
client.messages.create, then translates the response → AVP ModelResponse.

The driver is provider-agnostic at the AVP boundary: AVPAgent doesn't know it's
talking to Anthropic. Swap drivers, the rest of the loop is unchanged.
"""

from __future__ import annotations

import logging
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from avp import (
    COST_SOURCE_UNKNOWN,
    Commission,
    ModelPrice,
    PriceTable,
    compute_cost,
    load_default_prices,
)
from avp.agent.drivers import (
    ModelDriver,
    ModelResponse,
    ReasoningBlock,
    Refusal,
    ScriptedToolCall,
    ServerToolCall,
)

logger = logging.getLogger(__name__)


# ── Pricing (re-exports + lazy default) ───────────────────────────────────────
#
# `DEFAULT_PRICES` re-exports the bundled `avp` table (loaded once on first
# access) for backwards-compat with callers importing from this module.
# New code should import `load_default_prices()` directly from `avp`.

_DEFAULT_PRICES_CACHE: dict[str, ModelPrice] | None = None


def _default_prices() -> dict[str, ModelPrice]:
    global _DEFAULT_PRICES_CACHE
    if _DEFAULT_PRICES_CACHE is None:
        _DEFAULT_PRICES_CACHE = load_default_prices()
    return _DEFAULT_PRICES_CACHE


class _LazyPrices:
    """Module-level alias that resolves to the shared default table on first
    access. Lets `from avp_anthropic import DEFAULT_PRICES` keep working while
    the actual table lives in `avp.pricing`."""

    def __getitem__(self, key: str) -> ModelPrice:
        return _default_prices()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return _default_prices().get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in _default_prices()

    def __iter__(self):
        return iter(_default_prices())

    def __len__(self) -> int:
        return len(_default_prices())


DEFAULT_PRICES: PriceTable = _LazyPrices()  # type: ignore[assignment]


def _compute_cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_write: int,
    prices: PriceTable,
) -> float:
    """Backwards-compat wrapper around `avp.compute_cost` that warns and
    returns just the float (matching the historical signature). New code
    should call `avp.compute_cost` directly to receive the source tag too."""
    cost, source = compute_cost(
        model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        prices=prices,
    )
    if source == COST_SOURCE_UNKNOWN:
        warnings.warn(
            f"avp-anthropic: no price for model {model!r}; cost reported as 0.0", stacklevel=2
        )
    return cost


# ── Translation: AVP ↔ Anthropic ──────────────────────────────────────────────


def _avp_history_to_anthropic_messages(
    history: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Split AVP history into (system_prompt, messages[]) per Anthropic API shape.

    AVP history items:
        {role: "system", content: "..."}
        {role: "user",   content: "...", kind?: "observation"}
        {role: "assistant", content: "...", tool_calls: [{call_id, tool, input}, ...] | None}
        {role: "tool", tool, call_id, output}

    Assistant entries with tool_calls are rendered as Anthropic content blocks:
    a TextBlock for the text (if any) followed by a ToolUseBlock per call. The
    matching `role: tool` entries become user-role tool_result blocks. Sending
    the assistant turn is REQUIRED — otherwise the tool_result has no matching
    tool_use_id and the API rejects the next turn.
    """
    system: str | None = None
    messages: list[dict[str, Any]] = []
    for item in history:
        role = item.get("role")
        if role == "system":
            system = (system + "\n\n" if system else "") + str(item.get("content", ""))
        elif role == "user":
            messages.append({"role": "user", "content": str(item.get("content", ""))})
        elif role == "assistant":
            text = str(item.get("content", "") or "")
            tool_calls = item.get("tool_calls") or []
            if tool_calls:
                blocks: list[dict[str, Any]] = []
                if text:
                    blocks.append({"type": "text", "text": text})
                for tc in tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("call_id", ""),
                            "name": tc.get("tool", ""),
                            "input": tc.get("input", {}) or {},
                        }
                    )
                messages.append({"role": "assistant", "content": blocks})
            else:
                messages.append({"role": "assistant", "content": text})
        elif role == "tool":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": item.get("call_id", ""),
                            "content": str(item.get("output", "")),
                        }
                    ],
                }
            )
    return system, messages


# ── Block dispatch ──────────────────────────────────────────────────────────
#
# Anthropic's `Message.content` is a heterogeneous list of typed blocks
# (text, tool_use, thinking, mcp_tool_use, web_search_tool_use, …). Each
# block needs a small, focused mapping to AVP shape. We dispatch by block
# `.type` to a handler registered in `_BLOCK_HANDLERS` so adding a new
# block type is a one-line registration plus a small named function —
# no growth in branching control flow.
#
# Why string-key dispatch and not isinstance against `anthropic.types.*`:
# we accept duck-typed inputs (test fakes via SimpleNamespace, dict-shaped
# blocks from beta endpoints, vendored SDK forks). A future refactor can
# layer an `isinstance` lookup on top of this without touching call sites.


@dataclass
class _BlockAcc:
    """Mutable accumulator threaded through block handlers.

    Each handler reads one block and updates the relevant slice. MCP and
    hosted tools collect uses / results separately because the API can
    interleave them with other blocks in the response — we pair them
    after the visit pass.
    """

    text_parts: list[str] = field(default_factory=list)
    tool_calls: list[ScriptedToolCall] = field(default_factory=list)
    reasoning_blocks: list[ReasoningBlock] = field(default_factory=list)
    mcp_uses: dict[str, dict[str, Any]] = field(default_factory=dict)
    mcp_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    hosted_uses: dict[str, dict[str, Any]] = field(default_factory=dict)
    hosted_results: dict[str, dict[str, Any]] = field(default_factory=dict)


_BlockHandler = Callable[[Any, _BlockAcc], None]


def _h_text(block: Any, acc: _BlockAcc) -> None:
    acc.text_parts.append(getattr(block, "text", "") or "")


def _h_tool_use(block: Any, acc: _BlockAcc) -> None:
    acc.tool_calls.append(
        ScriptedToolCall(
            call_id=getattr(block, "id", "") or "",
            tool=getattr(block, "name", "") or "",
            input=dict(getattr(block, "input", {}) or {}),
        )
    )


def _h_thinking(block: Any, acc: _BlockAcc) -> None:
    """Extended-thinking block: chain-of-thought + signature for replay."""
    acc.reasoning_blocks.append(
        ReasoningBlock(
            text=getattr(block, "thinking", "") or "",
            signature=getattr(block, "signature", None) or None,
            redacted=False,
        )
    )


def _h_redacted_thinking(block: Any, acc: _BlockAcc) -> None:
    """Encrypted-only thinking: record the occurrence + signature so
    audit consumers can count thinking turns even without plaintext."""
    acc.reasoning_blocks.append(
        ReasoningBlock(
            text="",
            signature=getattr(block, "data", None) or None,
            redacted=True,
        )
    )


def _h_mcp_use(block: Any, acc: _BlockAcc) -> None:
    use_id = getattr(block, "id", "") or ""
    if not use_id:
        return
    acc.mcp_uses[use_id] = {
        "name": getattr(block, "name", "") or "",
        "server_name": getattr(block, "server_name", None),
        "input": dict(getattr(block, "input", {}) or {}),
    }


def _h_mcp_result(block: Any, acc: _BlockAcc) -> None:
    tu_id = getattr(block, "tool_use_id", "") or ""
    if not tu_id:
        return
    acc.mcp_results[tu_id] = {
        "is_error": bool(getattr(block, "is_error", False)),
        "content": getattr(block, "content", None),
    }


def _make_hosted_use_handler(subtype: str) -> _BlockHandler:
    """Hosted-tool uses (web_search, code_execution, …) share one parsing
    shape — only the `subtype` discriminator differs. Closure captures
    the subtype so the registry can wire one entry per block-type name."""

    def handler(block: Any, acc: _BlockAcc) -> None:
        use_id = getattr(block, "id", "") or ""
        if not use_id:
            return
        acc.hosted_uses[use_id] = {
            "name": getattr(block, "name", "") or subtype,
            "subtype": subtype,
            "input": dict(getattr(block, "input", {}) or {}),
        }

    return handler


def _h_hosted_result(block: Any, acc: _BlockAcc) -> None:
    """All hosted tool results share a shape — pair by `tool_use_id`."""
    tu_id = getattr(block, "tool_use_id", "") or ""
    if not tu_id:
        return
    acc.hosted_results[tu_id] = {
        "is_error": bool(getattr(block, "is_error", False)),
        "content": getattr(block, "content", None),
    }


# Block-type → handler. Adding a new type is one line plus a small
# named handler. Hosted tools register multiple block-type keys to
# closures that carry the subtype.
# Anthropic-API hosted server-side tools the agent KNOWS HOW to parse
# when the user opts them in via the API's tool-use mechanisms. Public:
# Commission authors building `cfg.allowed_tools` import this to surface what
# the agent can recognize on the wire if the API is configured to use
# hosted tools.
#
# Authoritative source of names: `claude_agent_sdk.ServerToolName` Literal
# (the SDK pins these as a typed enum of API-server-side tool names).
# Snapshot reflects current AVP agent block-parser support; new hosted
# tools the API ships need a matching `_BLOCK_HANDLERS` entry before they
# show up here.
ANTHROPIC_HOSTED_TOOL_KINDS: tuple[str, ...] = (
    "web_search",
    "code_execution",
    "bash_code_execution",
)


_BLOCK_HANDLERS: dict[str, _BlockHandler] = {
    "text": _h_text,
    "tool_use": _h_tool_use,
    "thinking": _h_thinking,
    "redacted_thinking": _h_redacted_thinking,
    "mcp_tool_use": _h_mcp_use,
    "mcp_tool_result": _h_mcp_result,
    "web_search_tool_use": _make_hosted_use_handler("web_search"),
    "web_search_tool_result": _h_hosted_result,
    "code_execution_tool_use": _make_hosted_use_handler("code_execution"),
    "code_execution_tool_result": _h_hosted_result,
    "bash_code_execution_tool_use": _make_hosted_use_handler("bash_code_execution"),
    "bash_code_execution_tool_result": _h_hosted_result,
}


def _anthropic_response_to_avp(
    response: Any, model: str, prices: PriceTable, duration_ms: int
) -> ModelResponse:
    """Translate an anthropic.types.Message → AVP ModelResponse.

    Walks `response.content`, dispatches each block to its handler in
    `_BLOCK_HANDLERS`, then assembles the final `ModelResponse`. The
    "what kinds of blocks exist" knowledge lives entirely in the
    handler registry; this function is just orchestration + accounting.
    """
    acc = _BlockAcc()
    for block in response.content or []:
        handler = _BLOCK_HANDLERS.get(getattr(block, "type", None))
        if handler is not None:
            handler(block, acc)
        # Unknown block types are silently ignored — defensive against
        # SDK upgrades that introduce new content types we haven't
        # mapped yet. Add an entry to _BLOCK_HANDLERS to surface them.

    text_parts = acc.text_parts
    tool_calls = acc.tool_calls
    reasoning_blocks = acc.reasoning_blocks
    server_tool_calls = _pair_mcp_blocks(acc.mcp_uses, acc.mcp_results) + _pair_hosted_blocks(
        acc.hosted_uses, acc.hosted_results
    )

    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)

    # AVP convention: tokens_input INCLUDES cache reads (they are input tokens).
    # The Anthropic SDK reports input_tokens as fresh-only, so add cache reads back.
    avp_tokens_input = input_tokens + cache_read + cache_write

    cost, cost_source = compute_cost(
        model,
        input_tokens=avp_tokens_input,
        output_tokens=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        prices=prices,
    )
    if cost_source == COST_SOURCE_UNKNOWN:
        warnings.warn(
            f"avp-anthropic: no price for model {model!r}; cost reported as 0.0", stacklevel=2
        )

    stop_reason = getattr(response, "stop_reason", None)
    refusal = _detect_refusal(stop_reason, response.content or [])
    converged = (stop_reason == "end_turn") and not tool_calls

    return ModelResponse(
        tokens_input=avp_tokens_input,
        tokens_output=output_tokens,
        cost_usd=cost,
        cost_source=cost_source,
        duration_ms=duration_ms,
        text=("".join(text_parts) or None) if text_parts else None,
        tool_calls=tool_calls,
        server_tool_calls=server_tool_calls,
        reasoning_blocks=reasoning_blocks,
        refusal=refusal,
        tokens_cache_read=cache_read or None,
        tokens_cache_write=cache_write or None,
        converged=converged,
    )


# Anthropic stop_reason values that indicate the model declined / was filtered.
# Verified against the public docs as of 2026-05; `sensitive` is observed in
# the wild but not yet documented (per community reports). Both flow into
# the same `Refusal` shape — downstream consumers filter by `avp.refusal.reason`
# if they care about the distinction.
_ANTHROPIC_REFUSAL_STOP_REASONS = {"refusal", "sensitive"}


def _detect_refusal(stop_reason: Any, content: list[Any]) -> Refusal | None:
    """Map Anthropic refusal-flavored signals to an AVP `Refusal`.

    Anthropic surfaces refusals via `stop_reason`. The response body
    sometimes carries a refusal-text content block; we render any
    text we find as `message` so consumers don't have to re-walk the
    content to get the model's stated reason. A `refusal` content block
    type is recognized first; failing that, plain text on a refused turn
    is treated as the message (some Anthropic responses inline the
    refusal text in a regular `text` block)."""
    if stop_reason not in _ANTHROPIC_REFUSAL_STOP_REASONS:
        return None
    message_parts: list[str] = []
    for block in content or []:
        btype = getattr(block, "type", None)
        if btype == "refusal":
            text = getattr(block, "text", None) or getattr(block, "refusal", None)
            if isinstance(text, str) and text:
                message_parts.append(text)
        elif btype == "text":
            text = getattr(block, "text", None)
            if isinstance(text, str) and text:
                message_parts.append(text)
    return Refusal(
        reason=str(stop_reason),
        message="\n".join(message_parts) or None,
        category=None,  # Anthropic doesn't expose a category enum
        provider="anthropic",
    )


def _pair_mcp_blocks(
    uses: dict[str, dict[str, Any]],
    results: dict[str, dict[str, Any]],
) -> list[ServerToolCall]:
    """Pair `mcp_tool_use` and `mcp_tool_result` blocks by tool_use_id
    and render result content to a single text snippet plus structured
    blocks. A `use` without a matching `result` becomes an error
    ServerToolCall (the API ran the call but the result didn't make it
    back) so the trajectory still records the attempt."""
    out: list[ServerToolCall] = []
    for use_id, use in uses.items():
        result = results.get(use_id)
        text, structured, is_error = _render_mcp_result(result)
        out.append(
            ServerToolCall(
                call_id=use_id,
                tool=use.get("name", "") or "",
                input=use.get("input", {}) or {},
                output_text=text,
                output_structured=structured,
                is_error=is_error,
                dispatch_target="mcp_server",
                server_id=use.get("server_name") or None,
            )
        )
    return out


def _render_mcp_result(
    result: dict[str, Any] | None,
) -> tuple[str, Any | None, bool]:
    """Flatten an `mcp_tool_result.content` block into (text, structured, is_error).

    `content` is typically a list of `{type: "text", text: "..."}` blocks
    (per the MCP spec) but vendors sometimes return a bare string. We
    keep the raw `content` as `structured` so downstream consumers can
    introspect, and join all text blocks for `output_text`. A missing
    result is treated as an error (the API didn't return one)."""
    if result is None:
        return ("missing mcp_tool_result block", None, True)
    content = result.get("content")
    is_error = bool(result.get("is_error", False))
    if isinstance(content, str):
        return (content, content, is_error)
    if isinstance(content, list):
        text = "\n".join(
            str(b.get("text", ""))
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
        return (text, content, is_error)
    return ("", content, is_error)


def _pair_hosted_blocks(
    uses: dict[str, dict[str, Any]],
    results: dict[str, dict[str, Any]],
) -> list[ServerToolCall]:
    """Pair `<subtype>_tool_use` and `<subtype>_tool_result` blocks by id.

    Same structure as MCP pairing but emits ServerToolCalls with
    `dispatch_target=local` and `subtype` set to the hosted-tool kind
    (web_search, code_execution, …). Result content shapes vary per
    tool — web_search returns a list of search-result blocks,
    code_execution returns a dict with stdout/stderr/return_code —
    so we render conservatively: text fields concatenated, otherwise
    JSON-coerced; the raw block lands in `output_structured`."""
    out: list[ServerToolCall] = []
    for use_id, use in uses.items():
        result = results.get(use_id)
        text, structured, is_error = _render_hosted_result(result)
        out.append(
            ServerToolCall(
                call_id=use_id,
                tool=use.get("name", "") or use.get("subtype", "") or "",
                input=use.get("input", {}) or {},
                output_text=text,
                output_structured=structured,
                is_error=is_error,
                dispatch_target="local",
                subtype=use.get("subtype"),
            )
        )
    return out


def _render_hosted_result(
    result: dict[str, Any] | None,
) -> tuple[str, Any | None, bool]:
    """Render a hosted-tool result block to (text, structured, is_error).

    Hosted-tool results are heterogeneous:
      - web_search: `content` is a list of result blocks (URL + snippet)
      - code_execution: `content` is a dict with stdout/stderr/return_code
      - bash_code_execution: similar to code_execution

    We extract a textual rendering for the wire's `avp.tool.result.text`
    and keep the raw content under `avp.tool.result.structured`. A missing
    result is treated as an error.
    """
    import json as _json

    if result is None:
        return ("missing hosted tool_result block", None, True)
    content = result.get("content")
    is_error = bool(result.get("is_error", False))
    if isinstance(content, str):
        return (content, content, is_error)
    if isinstance(content, list):
        # Likely web_search-style: list of result blocks.
        parts: list[str] = []
        for b in content:
            if isinstance(b, dict):
                # Pick the most useful textual field per result block.
                for key in ("text", "title", "url", "content"):
                    val = b.get(key)
                    if isinstance(val, str) and val:
                        parts.append(val)
                        break
        return ("\n".join(parts), content, is_error)
    if isinstance(content, dict):
        # code_execution-style: stdout/stderr/return_code.
        stdout = str(content.get("stdout", ""))
        stderr = str(content.get("stderr", ""))
        rc = content.get("return_code")
        text = stdout
        if stderr:
            text = (text + "\n" if text else "") + f"stderr: {stderr}"
        if rc is not None and rc != 0:
            text = (text + "\n" if text else "") + f"exit: {rc}"
            is_error = True
        if not text:
            text = _json.dumps(content)
        return (text, content, is_error)
    return ("", content, is_error)


# ── Driver ────────────────────────────────────────────────────────────────────


class AnthropicModelDriver(ModelDriver):
    """ModelDriver that routes each turn through the Anthropic Messages API.

    Construct with `model` (Claude model id), an optional Anthropic client (any
    object exposing `.messages.create(...)`; the real `anthropic.Anthropic()`
    works as does a unit-test mock), an optional `tools_param` list with the
    Anthropic tools[] schema (surfaces supervisor-declared and locally-declared
    tools to the model), an optional `mcp_servers_param` for Anthropic's
    server-side MCP connector, and an optional `prices` table to override
    DEFAULT_PRICES.

    `mcp_servers_param` is the API's MCP-connector shape — a list of
    `{type, name, url, ...}` dicts that the Anthropic API connects to and
    exposes as additional tools to the model. Translate from
    `Commission.mcp_servers[]` via `build_anthropic_mcp_servers(config)` —
    HTTP-only, since the API connector doesn't speak stdio.
    """

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        client: Any | None = None,
        tools_param: list[dict[str, Any]] | None = None,
        mcp_servers_param: list[dict[str, Any]] | None = None,
        prices: PriceTable | None = None,
        max_tokens: int = 4096,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self._client = client
        self.tools_param = tools_param
        self.mcp_servers_param = mcp_servers_param
        self.prices = prices or DEFAULT_PRICES
        self.max_tokens = max_tokens
        self.extra_kwargs = extra_kwargs or {}

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:  # pragma: no cover
                raise RuntimeError(
                    "avp-anthropic: install the `anthropic` SDK or pass a client explicitly"
                ) from e
            self._client = anthropic.Anthropic()
        return self._client

    def step(self, history: list[dict[str, Any]]) -> ModelResponse:
        system, messages = _avp_history_to_anthropic_messages(history)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if self.tools_param:
            kwargs["tools"] = self.tools_param
        if self.mcp_servers_param:
            kwargs["mcp_servers"] = self.mcp_servers_param
        kwargs.update(self.extra_kwargs)

        t0 = time.monotonic()
        response = self.client.messages.create(**kwargs)
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _anthropic_response_to_avp(response, self.model, self.prices, duration_ms)


# ── Commission → Anthropic tools[] translation ────────────────────────────────────


_DEFAULT_SUBAGENT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "Task description for the subagent."}
    },
    "required": ["prompt"],
}


def build_anthropic_tools(
    config: Commission,
    *,
    builtins: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build the `tools` parameter for Anthropic's Messages API from an AVP Commission.

    Merges two sources into one Anthropic-shaped tools[] list:
      1. `builtins` — agent-provided tools the driver always exposes (e.g.
         `avp_anthropic.shell_tools.SHELL_TOOL_SCHEMAS`). Pass `None` to omit.
      2. `config.subagents` — declared subagents become MCP-shaped tools the
         model can call by name. The agent routes the call through the
         subagent lifecycle on dispatch (NOT the tool lifecycle), but the
         model sees them as ordinary tools — this matches Claude Agent SDK,
         Google ADK AgentTool, and DeepAgents conventions.

    Applies `config.allowed_tools` as a final allowlist filter when set.

    Translates camelCase MCP `inputSchema` to snake_case `input_schema` (the
    Anthropic API's wire spelling) at the boundary.

    Use this whenever you wire `AVPAgent` directly with `AnthropicModelDriver`
    — without it, the model sees no tools at all and any subagent dispatch
    path is unreachable. The `avp-anthropic` CLI calls this for you;
    in-process callers (tests, custom supervisors) need to call it themselves.
    """
    out: list[dict[str, Any]] = list(builtins or [])
    if config.subagents:
        out.extend(
            {
                "name": sa.name,
                "description": sa.description,
                "input_schema": sa.inputSchema or _DEFAULT_SUBAGENT_INPUT_SCHEMA,
            }
            for sa in config.subagents
        )
    if config.allowed_tools is not None:
        allowed = set(config.allowed_tools)
        out = [t for t in out if t["name"] in allowed]
    return out


def build_anthropic_mcp_servers(config: Commission) -> list[dict[str, Any]]:
    """Translate `Commission.mcp_servers[]` to Anthropic's API MCP-connector shape.

    Anthropic's Messages API accepts an `mcp_servers` parameter — a list
    of `{type, name, url, ...}` dicts identifying remote MCP servers the
    API itself connects to during the request. The API runs the MCP loop
    internally (initialize, tools/list, tools/call) and returns the
    final assistant content with the tool calls embedded.

    HTTP-only: the API connector doesn't speak stdio. Stdio servers in
    `Commission.mcp_servers[]` are SKIPPED — host them from your supervisor
    instead and proxy via `Commission.tools[]` (supervisor-RPC dispatch),
    or wait for agent-side stdio support.

    HTTP auth with `token_env` is resolved at translation time so the
    secret never lands on the wire (Commission / events). When the env var
    isn't set, no authorization header is shipped.
    """
    import os as _os
    import warnings as _warnings

    out: list[dict[str, Any]] = []
    for s in config.mcp_servers or []:
        if s.transport != "http":
            _warnings.warn(
                f"avp-anthropic: skipping MCP server {s.id!r} — Anthropic's API "
                "MCP connector only supports HTTP transport. Run stdio servers "
                "from your supervisor and proxy via Commission.tools[] instead.",
                stacklevel=2,
            )
            continue
        entry: dict[str, Any] = {
            "type": "url",
            "name": s.id,
            "url": s.url,
        }
        if s.auth is not None:
            token = _os.environ.get(s.auth.token_env, "")
            if token:
                entry["authorization_token"] = token
        out.append(entry)
    return out
