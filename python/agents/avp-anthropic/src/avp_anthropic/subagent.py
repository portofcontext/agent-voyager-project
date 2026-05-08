"""AnthropicSubagentDriver — runs a declared Subagent's sub-loop on the
Anthropic Messages API and emits the nested events under the subagent's
frame span.

The driver shows the "transparent" subagent mode: every internal model turn
is observable on the parent's event stream as a `model_turn_started` /
`model_turn_ended` pair whose `parent_span_id` chains through the
subagent's frame span. This is the same wire shape Google ADK and
LangGraph produce — interleaved events, parent linkage via span/branch.
The Claude Agent SDK case (opaque subagents) is a degenerate version where
no internal events are emitted; the wire shape is identical, just thinner.

v0.1 scope: subagents are pure-LLM helpers (no tools, no skills, no
recursion). The Subagent type permits all of these — the agent-side
support is incremental and lands in subsequent versions. The wire shape
is fixed in v0.1 so consumers can rely on it now.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from avp.agent.drivers import SubagentOutcome
from avp.enums import StopReason
from avp.types import (
    ModelTurnEndedData,
    ModelTurnEndedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    RunStateSnapshot,
    Subagent,
    TextEmittedData,
    TextEmittedEvent,
    new_span_id,
    now_iso,
)
from avp_anthropic.driver import (
    DEFAULT_PRICES,
    AnthropicModelDriver,
    PriceTable,
)

_SUBAGENT_DEFAULT_MAX_STEPS = 10


class AnthropicSubagentDriver:
    """SubagentDriver that runs the sub-loop using the Anthropic Messages API.

    The parent agent instantiates this once and wires it through
    `AVPAgent(subagent_driver=...)`. On each invocation it:

      1. Builds a fresh history seeded with the subagent's system_prompt
         and the parent-supplied prompt (from `invocation_input["prompt"]`,
         falling back to a serialized form of the full input dict).
      2. Runs an AnthropicModelDriver scoped to `subagent.model` (falling
         back to a configured default), looping until the model converges.
         An internal soft cap (10 turns) prevents runaway loops.
      3. Emits `model_turn_started` / `model_turn_ended` / `text_emitted`
         events via `parent_observer`, parented under
         `parent_frame_span_id` so the trajectory reconstructs as a tree.
      4. Returns a SubagentOutcome with the final text and a usage rollup.

    The subagent's own tools/skills/sub-subagents are declared in the type
    but NOT dispatched in v0.1 — emitting a clear error if the Subagent
    declares them, so consumers know to upgrade rather than get silent
    skipping.
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        default_model: str = "claude-haiku-4-5-20251001",
        prices: PriceTable | None = None,
        max_tokens: int = 2048,
    ) -> None:
        self._client = client
        self._default_model = default_model
        self._prices = prices or DEFAULT_PRICES
        self._max_tokens = max_tokens

    def invoke(
        self,
        subagent: Subagent,
        invocation_input: dict[str, Any],
        *,
        parent_trace_id: str,
        parent_frame_span_id: str,
        parent_observer: Callable[[BaseModel], None],
    ) -> SubagentOutcome:
        if subagent.subagents or subagent.skills:
            return self._unsupported_outcome(
                "v0.1 prototype does not yet dispatch nested subagents or skills; "
                "declared but not exercised."
            )
        if subagent.inherit_tools:
            return self._unsupported_outcome(
                "v0.1 prototype does not implement subagent.inherit_tools=True yet."
            )

        prompt_text = self._extract_prompt(invocation_input)
        history: list[dict[str, Any]] = []
        if subagent.system_prompt:
            history.append({"role": "system", "content": subagent.system_prompt})
        history.append({"role": "user", "content": prompt_text})

        # Subagent runs until the model converges or returns a tool call
        # (the v0.1 prototype has no subagent tools). The hardcoded cap
        # below is a runaway-protection safety net only — keeps a stuck
        # subagent from looping forever; v0.1 has no spec mechanism for caps.
        max_steps = _SUBAGENT_DEFAULT_MAX_STEPS

        model_id = subagent.model or self._default_model
        driver = AnthropicModelDriver(
            model=model_id,
            client=self._client,
            tools_param=None,  # v0.1 prototype: pure-LLM helpers
            prices=self._prices,
            max_tokens=self._max_tokens,
        )

        # Per-invocation tally; aggregated into the parent's run state via
        # SubagentOutcome.usage when we return.
        cost_usd = 0.0
        total_tokens = 0
        tokens_input = 0
        tokens_output = 0
        cache_read = 0
        cache_write = 0
        last_text: str = ""

        t0 = time.monotonic()
        started_at = now_iso()
        # Default if neither model nor cap exits the loop — the safety
        # cap above hit, which we treat as converged with the last text.
        reason: StopReason = StopReason.converged

        for step in range(1, max_steps + 1):
            turn_span_id = new_span_id()
            self._emit(
                parent_observer,
                ModelTurnStartedEvent(
                    subject=None,
                    data=ModelTurnStartedData(
                        trace_id=parent_trace_id,
                        span_id=turn_span_id,
                        parent_span_id=parent_frame_span_id,
                        step=step,
                        **{"avp.context_messages": len(history)},
                    ),
                ),
            )

            response = driver.step(history)

            ended_kwargs: dict[str, Any] = {
                "gen_ai.usage.input_tokens": response.tokens_input,
                "gen_ai.usage.output_tokens": response.tokens_output,
                "gen_ai.usage.cache_read.input_tokens": response.tokens_cache_read,
                "gen_ai.usage.cache_creation.input_tokens": response.tokens_cache_write,
                "avp.cost_usd": response.cost_usd,
            }
            if response.response_model is not None:
                ended_kwargs["gen_ai.response.model"] = response.response_model
            if response.finish_reasons:
                ended_kwargs["gen_ai.response.finish_reasons"] = response.finish_reasons
            self._emit(
                parent_observer,
                ModelTurnEndedEvent(
                    subject=None,
                    data=ModelTurnEndedData(
                        trace_id=parent_trace_id,
                        span_id=turn_span_id,
                        parent_span_id=parent_frame_span_id,
                        step=step,
                        duration_ms=response.duration_ms,
                        **ended_kwargs,
                    ),
                ),
            )

            cost_usd += response.cost_usd
            total_tokens += response.tokens_input + response.tokens_output
            tokens_input += response.tokens_input
            tokens_output += response.tokens_output
            cache_read += response.tokens_cache_read or 0
            cache_write += response.tokens_cache_write or 0

            if response.text:
                last_text = response.text
                self._emit(
                    parent_observer,
                    TextEmittedEvent(
                        subject=None,
                        data=TextEmittedData(
                            trace_id=parent_trace_id,
                            span_id=new_span_id(),
                            parent_span_id=turn_span_id,
                            step=step,
                            **{"avp.text": response.text},
                        ),
                    ),
                )
                history.append({"role": "assistant", "content": response.text})

            if response.converged:
                reason = StopReason.converged
                break
            if response.tool_calls:
                # v0.1 prototype: subagents have no tools. If the model
                # tries one anyway, treat it as convergence with the
                # last text and surface a hint to the parent. Future
                # versions will dispatch through the subagent's tool
                # surface.
                reason = StopReason.converged
                break

        duration_ms = int((time.monotonic() - t0) * 1000)
        usage = RunStateSnapshot(
            total_cost_usd=cost_usd,
            total_tokens=total_tokens,
            total_turns=step,
            tokens_input_total=tokens_input or None,
            tokens_output_total=tokens_output or None,
            tokens_cache_read_total=cache_read or None,
            tokens_cache_write_total=cache_write or None,
            started_at=started_at,
            duration_ms=duration_ms,
        )

        return SubagentOutcome(
            text=last_text or "(subagent returned no text)",
            reason=reason,
            duration_ms=duration_ms,
            usage=usage,
        )

    @staticmethod
    def _extract_prompt(invocation_input: dict[str, Any]) -> str:
        """Coerce the parent model's invocation input to the subagent's
        opening user message. Convention: a `prompt` field is preferred;
        otherwise serialize the full dict so structured inputs still
        reach the subagent."""
        prompt = invocation_input.get("prompt")
        if isinstance(prompt, str) and prompt:
            return prompt
        # Structured input — pass it through as JSON so the subagent can
        # parse if its system_prompt knows the schema.
        import json

        return json.dumps(invocation_input, separators=(",", ":"))

    @staticmethod
    def _emit(observer: Callable[[BaseModel], None], event: BaseModel) -> None:
        observer(event)

    def _unsupported_outcome(self, message: str) -> SubagentOutcome:
        return SubagentOutcome(
            text="",
            reason=StopReason.error,
            duration_ms=0,
            usage=RunStateSnapshot(total_cost_usd=0.0, total_tokens=0, total_turns=0),
            error=message,
            error_code="unsupported_in_v0_1",
        )


__all__ = ["AnthropicSubagentDriver"]
