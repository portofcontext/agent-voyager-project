"""Mock drivers for tests and the conformance harness (v0.1)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from aep.enums import StopReason
from aep.runner.drivers import (
    ModelDriver,
    ModelResponse,
    ScriptedToolCall,
    SubagentDriver,
    SubagentOutcome,
    ToolDriver,
    ToolOutcome,
)
from aep.types import RunStateSnapshot, Subagent

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
                f"ScriptedModel exhausted after {self.idx} responses; runner asked for one more turn"
            )
        r = self.responses[self.idx]
        self.idx += 1
        return r


def parse_scripted_model(case_responses: list[dict[str, Any]]) -> ScriptedModel:
    out: list[ModelResponse] = []
    for r in case_responses:
        tool_calls = [
            ScriptedToolCall(call_id=tc["call_id"], tool=tc["tool"], input=tc.get("input", {}))
            for tc in r.get("tool_calls", []) or []
        ]
        out.append(
            ModelResponse(
                tokens_input=r["tokens_input"],
                tokens_output=r["tokens_output"],
                cost_usd=r["cost_usd"],
                duration_ms=r["duration_ms"],
                text=r.get("text"),
                tool_calls=tool_calls,
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


@dataclass
class _ScriptedStep:
    on_match: dict[str, Any]
    delay_ms: int = 0
    send: dict[str, Any] | None = None
    skip: bool = False


class ScriptedSupervisor:
    """Conformance-harness supervisor for v0.1.

    Handles two agent-initiated RPC kinds: `tool_exec` and `approval`.
    Both work the same way — script a step that matches an outgoing
    request event, send a response keyed by the matching id. No hook
    dispatch, no unsolicited messages.
    """

    def __init__(self, steps: list[dict[str, Any]] | None = None) -> None:
        self._steps: list[_ScriptedStep] = [
            _ScriptedStep(
                on_match=s["on"]["match"],
                delay_ms=s.get("delay_ms", 0),
                send=s.get("send"),
                skip=bool(s.get("skip", False)),
            )
            for s in (steps or [])
        ]
        self._tool_responses: dict[str, BaseModel | None] = {}
        self._approval_responses: dict[str, BaseModel | None] = {}

    @staticmethod
    def _matches(pattern: dict[str, Any], doc: dict[str, Any]) -> bool:
        for k, expected in pattern.items():
            if k not in doc:
                return False
            actual = doc[k]
            if isinstance(expected, dict) and isinstance(actual, dict):
                if not ScriptedSupervisor._matches(expected, actual):
                    return False
            elif expected != actual:
                return False
        return True

    @staticmethod
    def _substitute(node: Any, *, event: dict[str, Any]) -> Any:
        if isinstance(node, str):
            return ScriptedSupervisor._substitute_str(node, event=event)
        if isinstance(node, dict):
            return {k: ScriptedSupervisor._substitute(v, event=event) for k, v in node.items()}
        if isinstance(node, list):
            return [ScriptedSupervisor._substitute(v, event=event) for v in node]
        return node

    @staticmethod
    def _substitute_str(s: str, *, event: dict[str, Any]) -> str:
        import re

        from aep.types import now_iso

        def _navigate(cur: Any, parts: list[str]) -> Any:
            """Walk parts as nested dict keys. When a part doesn't resolve at
            the current level, try joining successive parts with dots to find
            a single dotted key (e.g. `data` then `aep.request_id`)."""
            i = 0
            while i < len(parts):
                if not isinstance(cur, dict):
                    raise KeyError(f"cannot navigate into non-dict at part {parts[i]!r}")
                # Greedy: try the longest dotted-key match first.
                for end in range(len(parts), i, -1):
                    candidate = ".".join(parts[i:end])
                    if candidate in cur:
                        cur = cur[candidate]
                        i = end
                        break
                else:
                    raise KeyError(f"no key resolving at part {parts[i]!r}")
            return cur

        def repl(m: re.Match[str]) -> str:
            expr = m.group(1).strip()
            if expr == "now":
                return now_iso()
            if expr == "run_id":
                # CloudEvents envelope carries run_id as `subject`.
                return str(event.get("subject", event.get("run_id", "")))
            if expr.startswith("event."):
                path = expr[len("event.") :].split(".")
                return str(_navigate(event, path))
            raise KeyError(f"unknown placeholder {{{{{expr}}}}}")

        return re.sub(r"\{\{([^}]+)\}\}", repl, s)

    def observe(self, event: BaseModel) -> None:
        from aep.types import (
            ApprovalResolvedEvent,
            ToolExecResolvedEvent,
            parse_supervisor_message,
        )

        # Supervisor-recorded RPC replies loop back here; ignore so we don't double-dispatch.
        if isinstance(event, ToolExecResolvedEvent | ApprovalResolvedEvent):
            return

        ev_dict = event.model_dump(mode="json", by_alias=True, exclude_none=True)

        for step in self._steps:
            if not self._matches(step.on_match, ev_dict):
                continue
            if step.delay_ms:
                time.sleep(step.delay_ms / 1000.0)
            if step.skip or step.send is None:
                # tool_exec_request carries `aep.request_id`; approval_requested
                # carries `aep.approval.id`. Either way, record a None into the
                # right table so the runner's wait sees a timeout.
                data = ev_dict.get("data") or {}
                ev_type = ev_dict.get("type")
                if ev_type == "aep.tool_exec_request":
                    req_id = data.get("aep.request_id")
                    if isinstance(req_id, str):
                        self._tool_responses[req_id] = None
                elif ev_type == "aep.approval_requested":
                    ap_id = data.get("aep.approval.id")
                    if isinstance(ap_id, str):
                        self._approval_responses[ap_id] = None
                continue
            payload = self._substitute(step.send, event=ev_dict)
            msg = parse_supervisor_message(payload)
            self._dispatch(msg, ev_dict)

    def _dispatch(self, msg: BaseModel, ev_dict: dict[str, Any]) -> None:
        from aep.types import ApprovalResolvedEvent, ToolExecResolvedEvent

        if isinstance(msg, ToolExecResolvedEvent):
            self._tool_responses[msg.data.aep_request_id] = msg
        elif isinstance(msg, ApprovalResolvedEvent):
            self._approval_responses[msg.data.aep_approval_id] = msg
        else:
            raise TypeError(f"unexpected SupervisorMessage subtype: {type(msg).__name__}")

    def _wait_for(
        self, table: dict[str, BaseModel | None], request_id: str, timeout_ms: int
    ) -> BaseModel | None:
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            if request_id in table:
                return table.pop(request_id)
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.005)

    def get_tool_exec_response(self, request_id: str, timeout_ms: int) -> BaseModel | None:
        return self._wait_for(self._tool_responses, request_id, timeout_ms)

    def get_approval_response(self, approval_id: str, timeout_ms: int) -> BaseModel | None:
        return self._wait_for(self._approval_responses, approval_id, timeout_ms)


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
