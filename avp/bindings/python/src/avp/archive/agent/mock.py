"""Mock drivers for tests and the conformance harness (v0.1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, JsonValue

from avp.agent.drivers import (
    ModelDriver,
    ModelResponse,
    ResolveError,
    ResolverDriver,
    ScriptedToolCall,
    SubagentSpawnOutcome,
    ToolDriver,
    ToolOutcome,
)
from avp.enums import StopReason
from avp.trajectory import ManagedKind, RunStateSnapshot

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


# ── Supervisor (event sink, no RPC) ──────────────────────────────────────────


class ScriptedSupervisor:
    """No-op event sink for the conformance harness.

    The supervisor never pushes mid-run messages to the agent — the
    harness still constructs one of these so AVPAgent has somewhere to
    call `observe()`. The constructor accepts a `steps` argument for
    backwards compatibility with older case files; nothing is dispatched
    off it in v0.1.
    """

    def __init__(self, steps: list[dict[str, Any]] | None = None) -> None:
        self._steps = list(steps or [])

    def observe(self, event: BaseModel) -> None:
        return None


# ── Resolver (canned outcomes by entry id) ───────────────────────────────────


class ScriptedResolver(ResolverDriver):
    """In-process `ResolverDriver` for tests and the conformance harness.

    `resolutions` maps `(kind, id)` → result dict returned from
    `resolve`. Entries can also carry an `error` field — when present,
    `resolve` raises `ResolveError(error, code=error_code)` instead of
    returning material, exercising the `managed_ref_resolve_failed`
    path. Lookup is keyed by id only when the kind-prefixed key is
    missing, which keeps simple cases concise.

    `subagent_spawns` maps subagent id → spawn outcome dict. The dict's
    fields parallel `SubagentSpawnOutcome` plus an optional `usage` block
    describing the child's `RunStateSnapshot` rollup.

    Both maps are checked at the per-call layer so missing entries
    surface as `ResolveError("no scripted result for id={id!r}")`,
    making test assertions read clearly.

    The resolver records every call into `calls_resolve` /
    `calls_spawn_subagent` so tests can assert "this id was resolved",
    "spawn was called with input X", etc.
    """

    def __init__(
        self,
        resolutions: dict[str, dict[str, Any]] | None = None,
        subagent_spawns: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._resolutions = dict(resolutions or {})
        self._subagent_spawns = dict(subagent_spawns or {})
        self.calls_resolve: list[tuple[ManagedKind, str, JsonValue]] = []
        self.calls_spawn_subagent: list[tuple[str, dict[str, Any]]] = []

    def _lookup_resolution(self, kind: ManagedKind, id_: str) -> dict[str, Any] | None:
        return self._resolutions.get(f"{kind}:{id_}") or self._resolutions.get(id_)

    def resolve(self, *, kind: ManagedKind, id: str, ref: JsonValue) -> dict[str, Any]:
        self.calls_resolve.append((kind, id, ref))
        spec = self._lookup_resolution(kind, id)
        if spec is None:
            raise ResolveError(
                f"ScriptedResolver: no canned resolution for kind={kind!r} id={id!r}",
                code="not_found",
            )
        if "error" in spec:
            raise ResolveError(spec["error"], code=spec.get("error_code"))
        return dict(spec.get("result") or {})

    def spawn_subagent(
        self,
        *,
        run_id: str,
        id: str,
        ref: JsonValue,
        input: dict[str, Any],
    ) -> SubagentSpawnOutcome:
        self.calls_spawn_subagent.append((id, dict(input)))
        spec = self._subagent_spawns.get(id) or {}
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
        return SubagentSpawnOutcome(
            child_run_id=str(spec.get("child_run_id", f"sub-{run_id}-{id}")),
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
    "ScriptedResolver",
    "ScriptedSupervisor",
    "ScriptedTools",
    "parse_scripted_model",
]
