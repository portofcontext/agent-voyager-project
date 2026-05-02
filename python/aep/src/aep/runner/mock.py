"""Mock drivers for tests and the conformance harness (v0.1)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from aep.runner.drivers import (
    ModelDriver,
    ModelResponse,
    ScriptedToolCall,
    ToolDriver,
    ToolOutcome,
)

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

    Only handles RPC replies (tool_exec_resolved, re_observation_resolved).
    No hook dispatch, no unsolicited messages.
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
        self._reobs_responses: dict[str, BaseModel | None] = {}

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

        def repl(m: re.Match[str]) -> str:
            expr = m.group(1).strip()
            if expr == "now":
                return now_iso()
            if expr == "run_id":
                return str(event.get("run_id", ""))
            if expr.startswith("event."):
                path = expr[len("event.") :].split(".")
                cur: Any = event
                for part in path:
                    if not isinstance(cur, dict) or part not in cur:
                        raise KeyError(
                            f"placeholder {{{{{expr}}}}} cannot resolve at part {part!r}"
                        )
                    cur = cur[part]
                return str(cur)
            raise KeyError(f"unknown placeholder {{{{{expr}}}}}")

        return re.sub(r"\{\{([^}]+)\}\}", repl, s)

    def observe(self, event: BaseModel) -> None:
        from aep.types import (
            ReObservationResolvedEvent,
            ToolExecResolvedEvent,
            parse_supervisor_message,
        )

        # Supervisor-recorded RPC replies loop back here; ignore so we don't double-dispatch.
        if isinstance(event, (ToolExecResolvedEvent, ReObservationResolvedEvent)):
            return

        ev_dict = event.model_dump(mode="json", exclude_none=True)

        for step in self._steps:
            if not self._matches(step.on_match, ev_dict):
                continue
            if step.delay_ms:
                time.sleep(step.delay_ms / 1000.0)
            if step.skip or step.send is None:
                req_id = ev_dict.get("request_id")
                if isinstance(req_id, str):
                    self._sentinel_skip(ev_dict.get("type"), req_id)
                continue
            payload = self._substitute(step.send, event=ev_dict)
            msg = parse_supervisor_message(payload)
            self._dispatch(msg, ev_dict)

    def _sentinel_skip(self, runner_event_type: str | None, request_id: str) -> None:
        if runner_event_type == "tool_exec_request":
            self._tool_responses[request_id] = None
        elif runner_event_type == "re_observation_request":
            self._reobs_responses[request_id] = None

    def _dispatch(self, msg: BaseModel, ev_dict: dict[str, Any]) -> None:
        from aep.types import ReObservationResolvedEvent, ToolExecResolvedEvent

        if isinstance(msg, ToolExecResolvedEvent):
            self._tool_responses[msg.request_id] = msg
        elif isinstance(msg, ReObservationResolvedEvent):
            self._reobs_responses[msg.request_id] = msg
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

    def get_re_observation_response(self, request_id: str, timeout_ms: int) -> BaseModel | None:
        return self._wait_for(self._reobs_responses, request_id, timeout_ms)


__all__ = [
    "ModelExhausted",
    "ScriptedModel",
    "ScriptedSupervisor",
    "ScriptedTools",
    "parse_scripted_model",
]
