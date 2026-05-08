"""Mock drivers for tests and the conformance harness (v0.1)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from avp.agent.drivers import (
    ModelDriver,
    ModelResponse,
    ScriptedToolCall,
    SubagentDriver,
    SubagentOutcome,
    ToolDriver,
    ToolOutcome,
)
from avp.enums import StopReason
from avp.types import RunStateSnapshot, Subagent

# ── Model ─────────────────────────────────────────────────────────────────────


class ModelExhausted(RuntimeError):
    pass


class ScriptedModel(ModelDriver):
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = list(responses)
        self.idx = 0

    def step(self, history: list[dict[str, Any]]) -> ModelResponse:
        if self.idx >= len(self.responses):
            raise ModelExhausted(
                f"ScriptedModel exhausted after {self.idx} responses; agent asked for one more turn"
            )
        r = self.responses[self.idx]
        self.idx += 1
        return r


def parse_scripted_model(case_responses: list[dict[str, Any]]) -> ScriptedModel:
    from avp.agent.drivers import ReasoningBlock, Refusal

    out: list[ModelResponse] = []
    for r in case_responses:
        tool_calls = [
            ScriptedToolCall(call_id=tc["call_id"], tool=tc["tool"], input=tc.get("input", {}))
            for tc in r.get("tool_calls", []) or []
        ]
        reasoning_blocks = [
            ReasoningBlock(
                text=rb.get("text", ""),
                signature=rb.get("signature"),
                redacted=bool(rb.get("redacted", False)),
            )
            for rb in r.get("reasoning_blocks", []) or []
        ]
        refusal_dict = r.get("refusal")
        refusal = (
            Refusal(
                reason=refusal_dict["reason"],
                message=refusal_dict.get("message"),
                category=refusal_dict.get("category"),
                provider=refusal_dict.get("provider"),
            )
            if refusal_dict
            else None
        )
        out.append(
            ModelResponse(
                tokens_input=r["tokens_input"],
                tokens_output=r["tokens_output"],
                cost_usd=r["cost_usd"],
                duration_ms=r["duration_ms"],
                text=r.get("text"),
                tool_calls=tool_calls,
                reasoning_blocks=reasoning_blocks,
                refusal=refusal,
                tokens_cache_read=r.get("tokens_cache_read"),
                tokens_cache_write=r.get("tokens_cache_write"),
                converged=bool(r.get("converged", False)),
            )
        )
    return ScriptedModel(out)


# ── Tools ─────────────────────────────────────────────────────────────────────


class ScriptedTools(ToolDriver):
    def __init__(self, mapping: dict[str, dict[str, Any]] | None = None) -> None:
        self.mapping = mapping or {}

    def is_local(self, tool: str) -> bool:
        return tool in self.mapping

    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome:
        spec = self.mapping.get(tool)
        if spec is None:
            return ToolOutcome(error=f"unknown tool {tool!r}")
        if "error" in spec:
            return ToolOutcome(error=spec["error"], duration_ms=spec.get("duration_ms", 1))
        return ToolOutcome(
            output=spec.get("output", ""),
            duration_ms=spec.get("duration_ms", 1),
        )


# ── Supervisor (RPC scripting only) ──────────────────────────────────────────


class ScriptedSupervisor:
    """No-op event sink for the conformance harness.

    v0.1 has no agent→supervisor RPC channel — the agent doesn't talk to
    the supervisor mid-run. The harness still constructs one of these so
    AVPAgent has somewhere to call `observe()`. The constructor accepts a
    `steps` argument for backwards compatibility with older case files;
    nothing is dispatched off it in v0.1.
    """

    def __init__(self, steps: list[dict[str, Any]] | None = None) -> None:
        self._steps = list(steps or [])

    def observe(self, event: BaseModel) -> None:
        return None


# ── Subagent (scripted outcomes for the conformance harness) ─────────────────


class ScriptedSubagentDriver(SubagentDriver):
    """SubagentDriver that returns canned outcomes by subagent name.

    `outcomes` maps subagent name → outcome dict, where the dict carries
    fields parallel to `SubagentOutcome` plus an optional `usage` block
    describing the subagent's RunStateSnapshot rollup. Used by conformance
    cases to exercise the subagent lifecycle deterministically without an
    LLM in the loop.

    Example:
        ScriptedSubagentDriver({
            "researcher": {
                "text": "found 3 handlers",
                "reason": "converged",
                "duration_ms": 50,
                "usage": {"total_cost_usd": 0.001, "total_tokens": 80, "total_turns": 1},
            }
        })
    """

    def __init__(self, outcomes: dict[str, dict[str, Any]] | None = None) -> None:
        self._outcomes = outcomes or {}
        self._invocations: list[tuple[str, dict[str, Any]]] = []

    def invoke(
        self,
        subagent: Subagent,
        invocation_input: dict[str, Any],
        *,
        parent_trace_id: str,
        parent_frame_span_id: str,
        parent_observer: Callable[[BaseModel], None],
    ) -> SubagentOutcome:
        # Record for assertion-by-inspection in tests.
        self._invocations.append((subagent.name, dict(invocation_input)))

        spec = self._outcomes.get(subagent.name) or {}
        usage_spec = spec.get("usage") or {}
        usage = RunStateSnapshot(
            total_cost_usd=float(usage_spec.get("total_cost_usd", 0.0)),
            total_tokens=int(usage_spec.get("total_tokens", 0)),
            total_turns=int(usage_spec.get("total_turns", 0)),
            tokens_input_total=usage_spec.get("tokens_input_total"),
            tokens_output_total=usage_spec.get("tokens_output_total"),
        )
        reason = spec.get("reason", StopReason.converged)
        if isinstance(reason, str):
            reason = StopReason(reason)
        return SubagentOutcome(
            text=str(spec.get("text", "")),
            structured=spec.get("structured"),
            reason=reason,
            duration_ms=int(spec.get("duration_ms", 1)),
            usage=usage,
            error=spec.get("error"),
            error_code=spec.get("error_code"),
        )


__all__ = [
    "ModelExhausted",
    "ScriptedModel",
    "ScriptedSubagentDriver",
    "ScriptedSupervisor",
    "ScriptedTools",
    "parse_scripted_model",
]
