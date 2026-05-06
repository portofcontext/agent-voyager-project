"""AnthropicModelDriver — implements aep.runner.ModelDriver against the Anthropic SDK.

Each call to .step(history) translates AEP history → Anthropic messages, invokes
client.messages.create, then translates the response → AEP ModelResponse.

The driver is provider-agnostic at the AEP boundary: AEPRunner doesn't know it's
talking to Anthropic. Swap drivers, the rest of the loop is unchanged.
"""

from __future__ import annotations

import logging
import time
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aep import Config
from aep.runner.drivers import ModelDriver, ModelResponse, ScriptedToolCall

logger = logging.getLogger(__name__)


# ── Pricing ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelPrice:
    """Per-1M-token pricing in USD."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


PriceTable = Mapping[str, ModelPrice]


DEFAULT_PRICES: dict[str, ModelPrice] = {
    "claude-opus-4-7": ModelPrice(input=15.0, output=75.0, cache_read=1.50, cache_write=18.75),
    "claude-sonnet-4-6": ModelPrice(input=3.0, output=15.0, cache_read=0.30, cache_write=3.75),
    "claude-haiku-4-5-20251001": ModelPrice(
        input=1.0, output=5.0, cache_read=0.10, cache_write=1.25
    ),
}


def _compute_cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_write: int,
    prices: PriceTable,
) -> float:
    """Compute billable cost in USD from a turn's token counts. Cache reads are
    cheaper input tokens; the AEP wire keeps `tokens_input` inclusive of cache
    reads but the cost reflects the discount."""
    p = prices.get(model)
    if p is None:
        warnings.warn(
            f"aep-anthropic: no price for model {model!r}; cost reported as 0.0", stacklevel=2
        )
        return 0.0
    # input_tokens here is the FRESH input portion (i.e. raw input minus cache reads/writes).
    fresh_input = max(0, input_tokens - cache_read - cache_write)
    return (
        fresh_input * p.input / 1_000_000
        + cache_read * p.cache_read / 1_000_000
        + cache_write * p.cache_write / 1_000_000
        + output_tokens * p.output / 1_000_000
    )


# ── Translation: AEP ↔ Anthropic ──────────────────────────────────────────────


def _aep_history_to_anthropic_messages(
    history: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Split AEP history into (system_prompt, messages[]) per Anthropic API shape.

    AEP history items:
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


def _anthropic_response_to_aep(
    response: Any, model: str, prices: PriceTable, duration_ms: int
) -> ModelResponse:
    """Translate an anthropic.types.Message → AEP ModelResponse."""
    text_parts: list[str] = []
    tool_calls: list[ScriptedToolCall] = []

    for block in response.content or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(getattr(block, "text", ""))
        elif btype == "tool_use":
            tool_calls.append(
                ScriptedToolCall(
                    call_id=getattr(block, "id", ""),
                    tool=getattr(block, "name", ""),
                    input=dict(getattr(block, "input", {}) or {}),
                )
            )
        # Other content block types are ignored; future versions may surface them.

    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)

    # AEP convention: tokens_input INCLUDES cache reads (they are input tokens).
    # The Anthropic SDK reports input_tokens as fresh-only, so add cache reads back.
    aep_tokens_input = input_tokens + cache_read + cache_write

    cost = _compute_cost(
        model=model,
        input_tokens=aep_tokens_input,
        output_tokens=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        prices=prices,
    )

    converged = (getattr(response, "stop_reason", None) == "end_turn") and not tool_calls

    return ModelResponse(
        tokens_input=aep_tokens_input,
        tokens_output=output_tokens,
        cost_usd=cost,
        duration_ms=duration_ms,
        text=("".join(text_parts) or None) if text_parts else None,
        tool_calls=tool_calls,
        tokens_cache_read=cache_read or None,
        tokens_cache_write=cache_write or None,
        converged=converged,
    )


# ── Driver ────────────────────────────────────────────────────────────────────


class AnthropicModelDriver(ModelDriver):
    """ModelDriver that routes each turn through the Anthropic Messages API.

    Construct with `model` (Claude model id), an optional Anthropic client (any
    object exposing `.messages.create(...)`; the real `anthropic.Anthropic()`
    works as does a unit-test mock), an optional `tools_param_provider` callback
    that returns the Anthropic tools[] schema for a given turn (so supervisor-
    declared and locally-declared tools are surfaced to the model), and an
    optional `prices` table to override DEFAULT_PRICES.
    """

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        client: Any | None = None,
        tools_param: list[dict[str, Any]] | None = None,
        prices: PriceTable | None = None,
        max_tokens: int = 4096,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self._client = client
        self.tools_param = tools_param
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
                    "aep-anthropic: install the `anthropic` SDK or pass a client explicitly"
                ) from e
            self._client = anthropic.Anthropic()
        return self._client

    def step(self, history: list[dict[str, Any]]) -> ModelResponse:
        system, messages = _aep_history_to_anthropic_messages(history)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if self.tools_param:
            kwargs["tools"] = self.tools_param
        kwargs.update(self.extra_kwargs)

        t0 = time.monotonic()
        response = self.client.messages.create(**kwargs)
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _anthropic_response_to_aep(response, self.model, self.prices, duration_ms)


# ── Config → Anthropic tools[] translation ────────────────────────────────────


_DEFAULT_SUBAGENT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "Task description for the subagent."}
    },
    "required": ["prompt"],
}


def build_anthropic_tools(
    config: Config,
    *,
    builtins: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build the `tools` parameter for Anthropic's Messages API from an AEP Config.

    Merges three sources into one Anthropic-shaped tools[] list:
      1. `builtins` — runner-provided tools the driver always exposes (e.g.
         `aep_anthropic.shell_tools.SHELL_TOOL_SCHEMAS`). Pass `None` to omit.
      2. `config.tools` — supervisor-declared RPC tools. Names + inputSchema
         come straight off the Config.
      3. `config.subagents` — declared subagents become MCP-shaped tools the
         model can call by name. The runner routes the call through the
         subagent lifecycle on dispatch (NOT the tool lifecycle), but the
         model sees them as ordinary tools — this matches Claude Agent SDK,
         Google ADK AgentTool, and DeepAgents conventions.

    Applies `config.allowed_tools` as a final allowlist filter when set.

    Translates camelCase MCP `inputSchema` to snake_case `input_schema` (the
    Anthropic API's wire spelling) at the boundary.

    Use this whenever you wire `AEPRunner` directly with `AnthropicModelDriver`
    — without it, the model sees no tools at all and any tool/subagent
    dispatch path is unreachable. The `aep-anthropic` CLI calls this for you;
    in-process callers (tests, custom supervisors) need to call it themselves.
    """
    out: list[dict[str, Any]] = list(builtins or [])
    if config.tools:
        out.extend(
            {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
            for t in config.tools
        )
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
