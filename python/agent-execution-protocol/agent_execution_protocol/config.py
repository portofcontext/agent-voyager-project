"""AEP config — the JSON object sent to a runner on stdin at startup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AepHook:
    """A supervisor callback point — the runner pauses here and waits for a verdict.

    When the runner reaches a hook trigger, it emits a ``hook_request`` event,
    pauses execution, and reads a ``hook_verdict`` from stdin. The supervisor
    receives the request, runs whatever checks it wants, and responds with a
    verdict: ``continue``, ``stop``, or ``inject`` (inject a message into the
    agent's context window). If no verdict arrives within ``timeout_ms``,
    ``default_verdict`` is applied.

    Triggers:
        on_start      — before the first model call
        on_stop       — after agent_stop is emitted
        on_turn_end   — after each model_turn_end
        always        — after every model turn and every tool result
        on_tool:<name> — after tool_result for the named tool, e.g. on_tool:bash
    """

    name: str
    trigger: str
    timeout_ms: int = 30000
    default_verdict: str = "continue"  # "continue" | "stop" | "inject"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "trigger": self.trigger,
            "timeout_ms": self.timeout_ms,
            "default_verdict": self.default_verdict,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AepHook":
        if "name" not in d:
            raise ValueError("AepHook missing required field: name")
        if "trigger" not in d:
            raise ValueError("AepHook missing required field: trigger")
        return cls(
            name=d["name"],
            trigger=d["trigger"],
            timeout_ms=d.get("timeout_ms", 30000),
            default_verdict=d.get("default_verdict", "continue"),
        )


@dataclass
class AepBoundary:
    """Execution limits the runner enforces.

    The runner stops the agent when any limit is reached, emitting `agent_stop`
    with reason ``"budget_exhausted"``, ``"turn_limit"``, or ``"token_limit"``.
    """

    max_cost_usd: float | None = None
    max_steps: int | None = None
    max_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.max_cost_usd is not None:
            d["max_cost_usd"] = self.max_cost_usd
        if self.max_steps is not None:
            d["max_steps"] = self.max_steps
        if self.max_tokens is not None:
            d["max_tokens"] = self.max_tokens
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AepBoundary":
        return cls(
            max_cost_usd=d.get("max_cost_usd"),
            max_steps=d.get("max_steps"),
            max_tokens=d.get("max_tokens"),
        )


@dataclass
class AepConfig:
    run_id: str
    schema_version: str = "0.2"
    model: str | None = None
    thread_id: str | None = None
    prompt: str | None = None
    system_prompt: str | None = None
    boundary: AepBoundary | None = None
    output_schema: dict | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    hooks: list[AepHook] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AepConfig":
        _require(d, "run_id")
        boundary_raw = d.get("boundary")
        boundary = AepBoundary.from_dict(boundary_raw) if boundary_raw else None
        hooks = [AepHook.from_dict(h) for h in d.get("hooks", [])]
        return cls(
            schema_version=d.get("schema_version", "0.2"),
            run_id=d["run_id"],
            thread_id=d.get("thread_id"),
            prompt=d.get("prompt"),
            system_prompt=d.get("system_prompt"),
            model=d.get("model"),
            boundary=boundary,
            output_schema=d.get("output_schema"),
            meta=d.get("meta", {}),
            tags=d.get("tags", []),
            hooks=hooks,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
        }
        if self.model is not None:
            d["model"] = self.model
        if self.thread_id is not None:
            d["thread_id"] = self.thread_id
        if self.prompt is not None:
            d["prompt"] = self.prompt
        if self.system_prompt is not None:
            d["system_prompt"] = self.system_prompt
        if self.boundary is not None:
            d["boundary"] = self.boundary.to_dict()
        if self.output_schema is not None:
            d["output_schema"] = self.output_schema
        if self.meta:
            d["meta"] = self.meta
        if self.tags:
            d["tags"] = self.tags
        if self.hooks:
            d["hooks"] = [h.to_dict() for h in self.hooks]
        return d


def _require(d: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"AEP config missing required fields: {missing}")
