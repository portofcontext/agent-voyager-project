"""AVPAgent — the v0.1 normative loop.

The agent runs inside the supervisor's declared environment. The Commission
carries supervisor-managed asset refs (mcp_servers, skills, subagents). The
agent dereferences each ref at startup via the AVP Resolver API
(see `spec/v0.1/resolver.md`) before the main loop runs; managed subagents
spawn on-demand via `avp.spawn_subagent` when the model invokes them.

Each emitted event is a CloudEvent 1.0 envelope carrying typed `data`. Span
identification (`trace_id`, `span_id`, `parent_span_id`) follows OpenTelemetry
conventions so the trajectory reconstructs as a span tree:

    agent span (root)                                       agent_started/stopped
    ├── managed_ref span (per resolve)                      managed_ref_resolved/failed
    ├── skill span                                          skill_loaded
    ├── error span                                          error_occurred (run-level)
    ├── model_turn span (per turn)                          model_turn_started/ended
    │   ├── text span                                       text_emitted
    │   ├── cost span                                       cost_recorded
    │   └── tool span (per tool call)                       tool_invoked/returned/failed
"""

from __future__ import annotations

import itertools
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from avp.agent.drivers import (
    ModelDriver,
    ModelDriverError,
    ResolveError,
    ResolverDriver,
    SupervisorDriver,
    ToolDriver,
    ToolOutcome,
)
from avp.enums import ErrorCode, StopReason
from avp.types import (
    ZERO_SPAN_ID,
    AgentDescribedData,
    AgentDescribedEvent,
    AgentDescriptor,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    Commission,
    CostRecordedData,
    CostRecordedEvent,
    ErrorOccurredData,
    ErrorOccurredEvent,
    ManagedKind,
    ManagedRefResolvedData,
    ManagedRefResolvedEvent,
    ManagedRefResolveFailedData,
    ManagedRefResolveFailedEvent,
    McpServerConnectedData,
    McpServerConnectedEvent,
    McpServerDisconnectedData,
    McpServerDisconnectedEvent,
    ModelTurnEndedData,
    ModelTurnEndedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    ReasoningEmittedData,
    ReasoningEmittedEvent,
    RefusalRecordedData,
    RefusalRecordedEvent,
    RunRequestedData,
    RunRequestedEvent,
    RunStateSnapshot,
    SkillLoadedData,
    SkillLoadedEvent,
    SubagentFailedData,
    SubagentFailedEvent,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentReturnedData,
    SubagentReturnedEvent,
    TextEmittedData,
    TextEmittedEvent,
    ToolFailedData,
    ToolFailedEvent,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    new_span_id,
    new_trace_id,
    now_iso,
)

MCP_PROTOCOL_VERSION = "2025-11-25"


# ── Local mutable state ──────────────────────────────────────────────────────


@dataclass
class _MutableState:
    started_at: str
    started_monotonic_ms: int
    total_turns: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    tokens_input_total: int = 0
    tokens_output_total: int = 0
    tokens_cache_read_total: int = 0
    tokens_cache_write_total: int = 0
    tools_invoked: dict[str, int] = field(default_factory=dict)

    def snapshot(self, now_monotonic_ms: int) -> RunStateSnapshot:
        return RunStateSnapshot(
            total_cost_usd=self.total_cost_usd,
            total_tokens=self.total_tokens,
            total_turns=self.total_turns,
            tokens_input_total=self.tokens_input_total or None,
            tokens_output_total=self.tokens_output_total or None,
            tokens_cache_read_total=self.tokens_cache_read_total or None,
            tokens_cache_write_total=self.tokens_cache_write_total or None,
            tools_invoked=dict(self.tools_invoked) or None,
            started_at=self.started_at,
            duration_ms=max(0, now_monotonic_ms - self.started_monotonic_ms),
        )


def _monotonic_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


# ── The agent ────────────────────────────────────────────────────────────────


class AVPAgent:
    """Reference AVP agent. v0.1 model: declarative environment, refs-only
    Commission, resolver-protocol-mediated runtime materialization."""

    def __init__(
        self,
        commission: Commission,
        model: ModelDriver,
        tools: ToolDriver,
        supervisor: SupervisorDriver,
        agent_builtin_tools: list[dict[str, Any]] | None = None,
        resolver: ResolverDriver | None = None,
        *,
        descriptor: AgentDescriptor | None = None,
        on_event: Callable[[BaseModel], None] | None = None,
    ) -> None:
        """`agent_builtin_tools` declares the agent's built-in tool catalog.
        Each entry is `{name, description, input_schema}` (snake_case, internal).
        Used to compute the effective tool surface for `agent_started.data.tools`.

        `resolver` is required iff the Commission carries any managed
        assets (`mcp_servers`, `skills`, or `subagents` non-empty). The
        resolver dereferences the opaque refs into the connection material /
        content / metadata the agent uses; managed subagents are also
        spawned through it on demand. When the Commission carries no
        managed assets, `resolver` MAY be None.

        `descriptor` is the agent's self-description (see
        `AgentDescriptor`). When provided, the agent opens the trajectory
        with the `run_requested` → `agent_described` prelude before
        `agent_started`. When None, the prelude is skipped — used by
        embedded callers (the in-process supervisor example, conformance
        harness) that drive AVPAgent against a synthetic Commission
        without a packaged agent identity. Top-level CLI invocations
        (e.g. `avp-claude-agent-sdk`, the reference avp-anthropic agent in
        `supervisors/simple-supervisor-example/examples/`) MUST pass a
        descriptor so the wire is complete.

        `on_event` is an optional callback invoked synchronously as each event
        is emitted, BEFORE it lands in `self.trajectory`. The agent still
        accumulates the trajectory in memory for in-process consumers (tests,
        the CLI's post-run summary); the callback is for streaming consumers
        (workers writing events to durable storage as they happen, multi-host
        supervisors observing the run live, etc.). The callback MUST NOT
        mutate the event; it runs on the agent's thread and any exception
        propagates out.
        """
        self.commission = commission
        self.model = model
        self.tools = tools
        self.supervisor = supervisor
        self._resolver = resolver
        self._descriptor = descriptor
        self._on_event = on_event
        self.trajectory: list[BaseModel | dict[str, Any]] = []
        self._history: list[dict[str, Any]] = []
        self._agent_builtin_tools = list(agent_builtin_tools or [])

        # Subagent ids (for runtime dispatch — model invokes by id, agent
        # routes through resolver.spawn_subagent).
        self._subagent_ids: set[str] = {sa.id for sa in (commission.subagents or [])}
        self._subagent_refs: dict[str, Any] = {sa.id: sa.ref for sa in (commission.subagents or [])}

        # Resolved metadata, populated by `_resolve_managed_assets`. Keyed by
        # the Commission entry's id. Skill content is loaded from
        # _resolved_skills[id]["content"] into the agent's history at startup.
        self._resolved_mcp_servers: dict[str, dict[str, Any]] = {}
        self._resolved_skills: dict[str, dict[str, Any]] = {}
        self._resolved_subagents: dict[str, dict[str, Any]] = {}

        self._sa_seq = itertools.count(1)
        self._next_subagent_invocation_id = lambda: f"sa-{next(self._sa_seq)}"

        # Span tree state. trace_id is allocated per run; agent_span_id is the
        # root span (lifetime = the run); turn / tool spans are nested.
        self._trace_id: str = new_trace_id()
        self._agent_span_id: str = new_span_id()
        self._current_turn_span_id: str | None = None
        self._tool_span_by_call_id: dict[str, str] = {}

    # ── Span helpers ───────────────────────────────────────────────────────

    def _own_span(self, parent_span_id: str) -> dict[str, str]:
        """Triple for an event that owns its own span (atomic observation)."""
        return {
            "trace_id": self._trace_id,
            "span_id": new_span_id(),
            "parent_span_id": parent_span_id,
        }

    def _shared_span(self, span_id: str, parent_span_id: str) -> dict[str, str]:
        """Triple for an event that participates in a multi-event span (e.g.,
        tool_invoked + tool_returned share one span describing one tool call)."""
        return {
            "trace_id": self._trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
        }

    # ── Emission ────────────────────────────────────────────────────────────

    def _emit(self, event: BaseModel) -> None:
        if self._on_event is not None:
            self._on_event(event)
        self.trajectory.append(event)
        self.supervisor.observe(event)

    def _emit_error(self, code: ErrorCode, message: str) -> None:
        self._emit(
            ErrorOccurredEvent(
                subject=self.commission.run_id,
                data=ErrorOccurredData(
                    **self._own_span(self._agent_span_id),
                    **{"avp.error.code": code, "avp.error.message": message},
                ),
            )
        )

    # ── Run lifecycle ───────────────────────────────────────────────────────

    def run(self) -> AgentStoppedEvent:
        state = _MutableState(
            started_at=now_iso(),
            started_monotonic_ms=_monotonic_ms(),
        )
        self._state = state

        self._emit_run_prelude()
        self._emit_agent_started()

        # Startup gates — each emits `error_occurred` + signals stop on failure.
        if not self._validate_supported_model():
            return self._emit_agent_stopped(StopReason.error)
        if not self._validate_resolver_present():
            return self._emit_agent_stopped(StopReason.error)
        if not self._validate_no_collisions():
            return self._emit_agent_stopped(StopReason.error)
        if not self._validate_enabled_builtins():
            return self._emit_agent_stopped(StopReason.error)

        # Resolve managed refs. Each successful resolution emits
        # `managed_ref_resolved`; any failure emits `managed_ref_resolve_failed`
        # and short-circuits with reason=error per spec/v0.1/resolver.md §5.
        if not self._resolve_managed_assets():
            return self._emit_agent_stopped(StopReason.error)

        # Notify the model driver that resolved material is available.
        # Drivers that build provider-side params from MCP connection
        # material (e.g. AnthropicModelDriver's MCP connector kwarg)
        # implement `set_resolved_assets` and pick it up here. Drivers
        # that don't care (no-op default) simply lack the method.
        set_resolved = getattr(self.model, "set_resolved_assets", None)
        if callable(set_resolved):
            set_resolved(
                mcp_servers=dict(self._resolved_mcp_servers),
                skills=dict(self._resolved_skills),
                subagents=dict(self._resolved_subagents),
            )

        # Post-resolve materialization
        self._emit_mcp_connections()
        self._inject_skill_bodies_to_history()
        self._emit_skills_loaded()

        self._main_loop()

        for ev in reversed(self.trajectory):
            if isinstance(ev, AgentStoppedEvent):
                return ev
        raise RuntimeError("AVPAgent: trajectory missing agent_stopped — invariant violation")

    # ── Startup gates ───────────────────────────────────────────────────────

    def _has_managed_assets(self) -> bool:
        c = self.commission
        return bool(c.mcp_servers or c.skills or c.subagents)

    def _validate_resolver_present(self) -> bool:
        """If the Commission carries managed assets but no ResolverDriver was
        supplied, fail-fast with `resolver_not_configured` (spec/v0.1/resolver.md §2).

        Production agents construct an HTTP-backed driver from
        `AVP_RESOLVER_URL` before calling AVPAgent; the agent itself only
        sees the injected driver."""
        if not self._has_managed_assets():
            return True
        if self._resolver is not None:
            return True
        self._emit_error(
            ErrorCode.resolver_not_configured,
            (
                "Commission carries managed assets but no ResolverDriver was "
                "supplied to AVPAgent (and AVP_RESOLVER_URL was not bootstrapped). "
                "Configure a resolver service per `spec/v0.1/resolver.md` §2."
            ),
        )
        return False

    def _validate_no_collisions(self) -> bool:
        """Detect id/name collisions between agent-internal contributions
        and Commission-declared entries. v0.1 covers:

          - `Commission.subagents[].id` ↔ agent built-in tool names
          - `Commission.subagents[].id` ↔ descriptor.built_in_subagents[].name
          - `Commission.mcp_servers[].id` ↔ descriptor.built_in_subagents[].name
            / built_in_tool names (the reference agent doesn't ship internal
            MCP servers, but the rule is uniform across asset kinds)

        Tool-name collisions across distinct resolved MCP servers are an
        agent-runtime concern (the MCP client layer namespaces them) and
        not enforced here. See `spec/v0.1/trajectory.md` §4.1."""
        commission = self.commission
        builtin_tool_names = {bt["name"] for bt in self._agent_builtin_tools}
        if self._descriptor is not None:
            builtin_tool_names |= {t.name for t in (self._descriptor.built_in_tools or [])}
            builtin_subagent_names = {s.name for s in (self._descriptor.built_in_subagents or [])}
        else:
            builtin_subagent_names = set()
        commission_subagent_ids = {sa.id for sa in (commission.subagents or [])}
        commission_mcp_ids = {m.id for m in (commission.mcp_servers or [])}

        collisions: list[str] = []
        for entry_id in commission_subagent_ids & builtin_tool_names:
            collisions.append(f"subagent id {entry_id!r} collides with a built-in tool name")
        for entry_id in commission_subagent_ids & builtin_subagent_names:
            collisions.append(
                f"subagent id {entry_id!r} collides with a descriptor-declared built-in subagent"
            )
        for entry_id in commission_mcp_ids & builtin_tool_names:
            collisions.append(f"mcp_server id {entry_id!r} collides with a built-in tool name")
        for entry_id in commission_mcp_ids & builtin_subagent_names:
            collisions.append(
                f"mcp_server id {entry_id!r} collides with a descriptor-declared built-in subagent"
            )
        if not collisions:
            return True
        self._emit_error(
            ErrorCode.commission_collision,
            "; ".join(collisions),
        )
        return False

    def _validate_enabled_builtins(self) -> bool:
        """Validate `Commission.enabled_builtin_*` allowlists against the
        agent's descriptor-published built-in surfaces. Names that don't
        match any descriptor entry are configuration mistakes and fail-fast.

        Each list is independent: absent → all built-ins of that kind
        exposed; present → only the listed names exposed; `[]` → none of
        that kind exposed. The runtime block in `_handle_tool_call` /
        `_handle_subagent_call` enforces the same set when the model
        attempts to invoke a hidden built-in.
        """
        commission = self.commission
        unknown: list[str] = []

        # Resolve the source-of-truth name sets. The Descriptor is authoritative
        # when present; the constructor's `agent_builtin_tools` is the
        # fallback for the tool list (the reference agent's embedders pass
        # tools directly without a Descriptor). Subagents and skills only
        # have a Descriptor source — there's no constructor-arg equivalent.
        if self._descriptor is not None and self._descriptor.built_in_tools is not None:
            known_tools = {t.name for t in self._descriptor.built_in_tools}
        else:
            known_tools = {bt["name"] for bt in self._agent_builtin_tools}
        if self._descriptor is not None and self._descriptor.built_in_subagents is not None:
            known_subagents = {s.name for s in self._descriptor.built_in_subagents}
        else:
            known_subagents = set()
        if self._descriptor is not None and self._descriptor.built_in_skills is not None:
            known_skills = {s.name for s in self._descriptor.built_in_skills}
        else:
            known_skills = set()

        for name in commission.enabled_builtin_tools or []:
            if name not in known_tools:
                unknown.append(f"enabled_builtin_tools: {name!r} not in agent's built-in tools")
        for name in commission.enabled_builtin_subagents or []:
            if name not in known_subagents:
                unknown.append(
                    f"enabled_builtin_subagents: {name!r} not in agent's built-in subagents"
                )
        for name in commission.enabled_builtin_skills or []:
            if name not in known_skills:
                unknown.append(f"enabled_builtin_skills: {name!r} not in agent's built-in skills")

        if not unknown:
            return True
        self._emit_error(ErrorCode.commission_collision, "; ".join(unknown))
        return False

    def _is_builtin_tool_enabled(self, name: str) -> bool:
        """Return True if a built-in tool name passes
        `Commission.enabled_builtin_tools`. Absent allowlist = all enabled."""
        allow = self.commission.enabled_builtin_tools
        if allow is None:
            return True
        return name in allow

    def _is_builtin_subagent_enabled(self, name: str) -> bool:
        """Return True if a built-in subagent name passes
        `Commission.enabled_builtin_subagents`. Absent allowlist = all enabled."""
        allow = self.commission.enabled_builtin_subagents
        if allow is None:
            return True
        return name in allow

    def _is_builtin_skill_enabled(self, name: str) -> bool:
        """Return True if a built-in skill name passes
        `Commission.enabled_builtin_skills`. Absent allowlist = all enabled."""
        allow = self.commission.enabled_builtin_skills
        if allow is None:
            return True
        return name in allow

    def _validate_supported_model(self) -> bool:
        """Cross-check Commission.model against the agent's
        descriptor.supported_models (glob list). Skipped when no Descriptor is
        published, when the Descriptor declares no constraint, or when the
        Commission omits `model`."""
        import fnmatch

        commission = self.commission
        descriptor = self._descriptor
        if descriptor is None or descriptor.supported_models is None:
            return True
        if not commission.model:
            return True
        if any(fnmatch.fnmatchcase(commission.model, p) for p in descriptor.supported_models):
            return True
        self._emit_error(
            ErrorCode.unsupported_model,
            (
                f"Commission.model={commission.model!r} is not supported by "
                f"{descriptor.agent_name}@{descriptor.agent_version}; "
                f"supported_models={descriptor.supported_models}"
            ),
        )
        return False

    # ── Resolver loop ───────────────────────────────────────────────────────

    def _resolve_managed_assets(self) -> bool:
        """Walk every Commission-declared managed asset and call the
        resolver for each. On success, store the returned material in the
        agent's per-kind metadata maps and emit `managed_ref_resolved`. On
        any failure, emit `managed_ref_resolve_failed` and return False so
        the run terminates with reason=error.

        Resolution order: mcp_servers, then skills, then subagents. Within
        each kind, declaration order. The agent emits one event per ref;
        consumers correlate by `avp.managed.kind` + `avp.managed.id`.
        """
        commission = self.commission
        if not self._has_managed_assets():
            return True
        # `_validate_resolver_present` already fired before this; if we
        # reached here `_resolver` is non-None.
        assert self._resolver is not None

        for entry in commission.mcp_servers or []:
            ok, material = self._resolve_one("mcp_server", entry.id, entry.ref)
            if not ok:
                return False
            self._resolved_mcp_servers[entry.id] = material

        for entry in commission.skills or []:
            ok, material = self._resolve_one("skill", entry.id, entry.ref)
            if not ok:
                return False
            self._resolved_skills[entry.id] = material

        for entry in commission.subagents or []:
            ok, material = self._resolve_one("subagent", entry.id, entry.ref)
            if not ok:
                return False
            self._resolved_subagents[entry.id] = material

        return True

    def _resolve_one(
        self, kind: ManagedKind, entry_id: str, ref: Any
    ) -> tuple[bool, dict[str, Any]]:
        commission = self.commission
        assert self._resolver is not None
        t0 = _time.monotonic()
        try:
            material = self._resolver.resolve(kind=kind, id=entry_id, ref=ref)
        except ResolveError as e:
            duration_ms = max(0, int((_time.monotonic() - t0) * 1000))
            failed_kwargs: dict[str, Any] = {
                "avp.managed.kind": kind,
                "avp.managed.id": entry_id,
                "avp.resolve.error": str(e),
            }
            if e.code is not None:
                failed_kwargs["avp.resolve.error.code"] = e.code
            self._emit(
                ManagedRefResolveFailedEvent(
                    subject=commission.run_id,
                    data=ManagedRefResolveFailedData(
                        **self._own_span(self._agent_span_id),
                        **failed_kwargs,
                    ),
                )
            )
            return False, {}
        except Exception as e:
            duration_ms = max(0, int((_time.monotonic() - t0) * 1000))
            self._emit(
                ManagedRefResolveFailedEvent(
                    subject=commission.run_id,
                    data=ManagedRefResolveFailedData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "avp.managed.kind": kind,
                            "avp.managed.id": entry_id,
                            "avp.resolve.error": f"{type(e).__name__}: {e}",
                            "avp.resolve.error.code": "driver_exception",
                        },
                    ),
                )
            )
            return False, {}

        duration_ms = max(0, int((_time.monotonic() - t0) * 1000))
        self._emit(
            ManagedRefResolvedEvent(
                subject=commission.run_id,
                data=ManagedRefResolvedData(
                    **self._own_span(self._agent_span_id),
                    **{
                        "avp.managed.kind": kind,
                        "avp.managed.id": entry_id,
                        "duration_ms": duration_ms,
                    },
                ),
            )
        )
        return True, dict(material) if material else {}

    # ── Main loop ───────────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        state = self._state
        commission = self.commission

        while True:
            state.total_turns += 1
            self._current_turn_span_id = new_span_id()
            self._emit(
                ModelTurnStartedEvent(
                    subject=commission.run_id,
                    data=ModelTurnStartedData(
                        **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                        step=state.total_turns,
                        **{"avp.context_messages": len(self._history)},
                    ),
                )
            )
            try:
                response = self.model.step(self._history)
            except ModelDriverError as e:
                self._emit(
                    ModelTurnEndedEvent(
                        subject=commission.run_id,
                        data=ModelTurnEndedData(
                            **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                            step=state.total_turns,
                            duration_ms=0,
                            **{
                                "gen_ai.usage.input_tokens": 0,
                                "gen_ai.usage.output_tokens": 0,
                                "avp.cost_usd": 0.0,
                            },
                        ),
                    )
                )
                self._emit_error(e.code, str(e))
                self._emit_agent_stopped(StopReason.error)
                return

            ended_kwargs: dict[str, Any] = {
                "gen_ai.usage.input_tokens": response.tokens_input,
                "gen_ai.usage.output_tokens": response.tokens_output,
                "gen_ai.usage.cache_read.input_tokens": response.tokens_cache_read,
                "gen_ai.usage.cache_creation.input_tokens": response.tokens_cache_write,
                "gen_ai.usage.reasoning.output_tokens": response.tokens_reasoning_output,
                "avp.cost_usd": response.cost_usd,
                "avp.cost.source": response.cost_source,
            }
            if response.response_model is not None:
                ended_kwargs["gen_ai.response.model"] = response.response_model
            if response.finish_reasons:
                ended_kwargs["gen_ai.response.finish_reasons"] = response.finish_reasons
            if response.time_to_first_chunk_s is not None:
                ended_kwargs["gen_ai.response.time_to_first_chunk"] = response.time_to_first_chunk_s
            self._emit(
                ModelTurnEndedEvent(
                    subject=commission.run_id,
                    data=ModelTurnEndedData(
                        **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                        step=state.total_turns,
                        duration_ms=response.duration_ms,
                        **ended_kwargs,
                    ),
                )
            )

            state.total_cost_usd += response.cost_usd
            state.total_tokens += response.tokens_input + response.tokens_output
            state.tokens_input_total += response.tokens_input
            state.tokens_output_total += response.tokens_output
            if response.tokens_cache_read:
                state.tokens_cache_read_total += response.tokens_cache_read
            if response.tokens_cache_write:
                state.tokens_cache_write_total += response.tokens_cache_write

            self._emit(
                CostRecordedEvent(
                    subject=commission.run_id,
                    data=CostRecordedData(
                        **self._own_span(self._current_turn_span_id),
                        **{"avp.state": state.snapshot(_monotonic_ms())},
                    ),
                )
            )

            for rb in response.reasoning_blocks:
                reasoning_kwargs: dict[str, Any] = {"avp.reasoning.text": rb.text}
                if rb.signature:
                    reasoning_kwargs["avp.reasoning.signature"] = rb.signature
                if rb.redacted:
                    reasoning_kwargs["avp.reasoning.redacted"] = rb.redacted
                self._emit(
                    ReasoningEmittedEvent(
                        subject=commission.run_id,
                        data=ReasoningEmittedData(
                            **self._own_span(self._current_turn_span_id),
                            step=state.total_turns,
                            **reasoning_kwargs,
                        ),
                    )
                )

            if response.text:
                self._emit(
                    TextEmittedEvent(
                        subject=commission.run_id,
                        data=TextEmittedData(
                            **self._own_span(self._current_turn_span_id),
                            step=state.total_turns,
                            **{"avp.text": response.text},
                        ),
                    )
                )

            if response.refusal is not None:
                refusal_kwargs: dict[str, Any] = {
                    "avp.refusal.reason": response.refusal.reason,
                }
                if response.refusal.message:
                    refusal_kwargs["avp.refusal.message"] = response.refusal.message
                if response.refusal.category:
                    refusal_kwargs["avp.refusal.category"] = response.refusal.category
                if response.refusal.provider:
                    refusal_kwargs["avp.refusal.provider"] = response.refusal.provider
                self._emit(
                    RefusalRecordedEvent(
                        subject=commission.run_id,
                        data=RefusalRecordedData(
                            **self._own_span(self._current_turn_span_id),
                            step=state.total_turns,
                            **refusal_kwargs,
                        ),
                    )
                )
                self._emit_agent_stopped(StopReason.refused)
                return

            for stc in response.server_tool_calls:
                self._emit_server_tool_call(stc, state)

            if response.text or response.tool_calls:
                self._history.append(
                    {
                        "role": "assistant",
                        "content": response.text or "",
                        "tool_calls": [
                            {"call_id": tc.call_id, "tool": tc.tool, "input": tc.input}
                            for tc in response.tool_calls
                        ]
                        if response.tool_calls
                        else None,
                    }
                )

            for tc in response.tool_calls:
                self._handle_tool_call(tc, state)

            if response.converged:
                self._emit_agent_stopped(StopReason.converged)
                return

    # ── Tool / subagent dispatch ────────────────────────────────────────────

    def _emit_tool_failed(self, tc, state: _MutableState, error: str) -> None:
        commission = self.commission
        tool_span_id = self._tool_span_by_call_id.get(tc.call_id) or new_span_id()
        self._emit(
            ToolFailedEvent(
                subject=commission.run_id,
                data=ToolFailedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    step=state.total_turns,
                    **{
                        "gen_ai.tool.call.id": tc.call_id,
                        "gen_ai.tool.name": tc.tool,
                        "avp.tool.error": error,
                    },
                ),
            )
        )
        self._history.append(
            {
                "role": "tool",
                "tool": tc.tool,
                "call_id": tc.call_id,
                "output": f"Error: {error}",
            }
        )

    def _emit_server_tool_call(self, stc, state: _MutableState) -> None:
        commission = self.commission
        tool_span_id = new_span_id()
        invoked_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": stc.call_id,
            "gen_ai.tool.name": stc.tool,
            "gen_ai.tool.call.arguments": dict(stc.input),
            "avp.tool.dispatch_target": stc.dispatch_target,
        }
        if stc.server_id:
            invoked_kwargs["avp.mcp_server_id"] = stc.server_id
        self._emit(
            ToolInvokedEvent(
                subject=commission.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    step=state.total_turns,
                    **invoked_kwargs,
                ),
            )
        )
        if stc.is_error:
            self._emit(
                ToolFailedEvent(
                    subject=commission.run_id,
                    data=ToolFailedData(
                        **self._shared_span(tool_span_id, self._current_turn_span_id),
                        step=state.total_turns,
                        **{
                            "gen_ai.tool.call.id": stc.call_id,
                            "gen_ai.tool.name": stc.tool,
                            "avp.tool.error": stc.output_text or "server-side tool reported error",
                        },
                    ),
                )
            )
            return
        returned_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": stc.call_id,
            "gen_ai.tool.name": stc.tool,
            "avp.tool.result.text": stc.output_text,
        }
        if stc.output_structured is not None:
            returned_kwargs["avp.tool.result.structured"] = stc.output_structured
        self._emit(
            ToolReturnedEvent(
                subject=commission.run_id,
                data=ToolReturnedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    step=state.total_turns,
                    duration_ms=stc.duration_ms,
                    **returned_kwargs,
                ),
            )
        )

    def _handle_tool_call(self, tc, state: _MutableState) -> None:
        commission = self.commission

        # Subagent dispatch — the model invoked a tool whose name matches a
        # Commission-declared subagent id. Routes through the resolver
        # (avp.spawn_subagent) and emits subagent_invoked / subagent_returned.
        if tc.tool in self._subagent_ids:
            self._handle_subagent_call(tc, state)
            return

        tool_span_id = new_span_id()
        self._tool_span_by_call_id[tc.call_id] = tool_span_id

        is_local = self.tools.is_local(tc.tool)
        dispatch_target = "local" if is_local else None

        invoked_data_kwargs: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.tool.call.id": tc.call_id,
            "gen_ai.tool.name": tc.tool,
            "gen_ai.tool.call.arguments": tc.input,
        }
        if dispatch_target is not None:
            invoked_data_kwargs["avp.tool.dispatch_target"] = dispatch_target

        self._emit(
            ToolInvokedEvent(
                subject=commission.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    **invoked_data_kwargs,
                ),
            )
        )
        state.tools_invoked[tc.tool] = state.tools_invoked.get(tc.tool, 0) + 1

        # Defense-in-depth allowlist enforcement. _build_tool_decls already
        # hides disabled built-ins from the model's tool catalog; if the
        # model invokes one anyway (hallucination, prompt injection from
        # tool output, prior-context leakage), refuse to execute and
        # record the attempt on the wire as tool_failed.
        if is_local and not self._is_builtin_tool_enabled(tc.tool):
            self._emit_tool_failed(
                tc,
                state,
                f"tool {tc.tool!r} disabled by Commission.enabled_builtin_tools",
            )
            return

        if not is_local:
            self._emit_tool_failed(tc, state, f"unknown tool {tc.tool!r}")
            return

        outcome: ToolOutcome = self.tools.invoke(tc.tool, tc.input)
        if outcome.error is not None and not outcome.rejected:
            self._emit_tool_failed(tc, state, outcome.error)
            return

        out_str = outcome.output if outcome.output is not None else ""
        returned_kwargs: dict[str, Any] = {
            "step": state.total_turns,
            "duration_ms": outcome.duration_ms,
            "gen_ai.tool.call.id": tc.call_id,
            "gen_ai.tool.name": tc.tool,
            "avp.tool.result.text": out_str,
        }
        if outcome.output_json is not None:
            returned_kwargs["avp.tool.result.structured"] = outcome.output_json
        if outcome.rejected:
            returned_kwargs["avp.tool.rejected"] = True
        if outcome.rejection_reason:
            returned_kwargs["avp.tool.rejection_reason"] = outcome.rejection_reason

        self._emit(
            ToolReturnedEvent(
                subject=commission.run_id,
                data=ToolReturnedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    **returned_kwargs,
                ),
            )
        )
        self._history.append(
            {
                "role": "tool",
                "tool": tc.tool,
                "call_id": tc.call_id,
                "output": out_str,
            }
        )

    def _handle_subagent_call(self, tc, state: _MutableState) -> None:
        """Dispatch a parent-agent tool call to a Commission-declared
        managed subagent. Calls the resolver's `spawn_subagent`, then
        emits `subagent_invoked` (carrying the child `run_id`) and either
        `subagent_returned` or `subagent_failed` depending on the outcome."""
        commission = self.commission
        sa_id = tc.tool
        ref = self._subagent_refs[sa_id]
        meta = self._resolved_subagents.get(sa_id) or {}
        invocation_id = self._next_subagent_invocation_id()
        frame_span_id = new_span_id()
        self._tool_span_by_call_id[tc.call_id] = frame_span_id
        state.tools_invoked[sa_id] = state.tools_invoked.get(sa_id, 0) + 1

        # `_validate_resolver_present` runs before any tool dispatch; if we
        # got here with managed assets in the Commission, `_resolver` is
        # non-None.
        assert self._resolver is not None

        t0 = _time.monotonic()
        try:
            outcome = self._resolver.spawn_subagent(
                run_id=commission.run_id,
                id=sa_id,
                ref=ref,
                input=dict(tc.input or {}),
            )
        except Exception as e:
            duration_ms = max(0, int((_time.monotonic() - t0) * 1000))
            self._emit_subagent_invoked_then_failed(
                tc=tc,
                state=state,
                meta=meta,
                invocation_id=invocation_id,
                frame_span_id=frame_span_id,
                error=f"{type(e).__name__}: {e}",
                error_code="resolver_exception",
                duration_ms=duration_ms,
                child_run_id=None,
            )
            return

        # Open the subagent frame on the wire.
        invoked_data: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.agent.name": meta.get("name", sa_id),
            "avp.subagent.invocation_id": invocation_id,
            "avp.subagent.input": dict(tc.input or {}),
            "avp.subagent.run_id": outcome.child_run_id,
        }
        description = meta.get("description")
        if description:
            invoked_data["gen_ai.agent.description"] = description
        self._emit(
            SubagentInvokedEvent(
                subject=commission.run_id,
                data=SubagentInvokedData(
                    **self._shared_span(frame_span_id, self._current_turn_span_id),
                    **invoked_data,
                ),
            )
        )

        # Roll the child's spend into the parent's state. Per-subagent
        # attribution is preserved on subagent_returned.data.avp.subagent.usage.
        child_usage = outcome.usage
        state.total_cost_usd += child_usage.total_cost_usd
        state.total_tokens += child_usage.total_tokens
        state.tokens_input_total += child_usage.tokens_input_total or 0
        state.tokens_output_total += child_usage.tokens_output_total or 0
        if child_usage.tokens_cache_read_total:
            state.tokens_cache_read_total += child_usage.tokens_cache_read_total
        if child_usage.tokens_cache_write_total:
            state.tokens_cache_write_total += child_usage.tokens_cache_write_total

        if outcome.error is not None:
            failed_data: dict[str, Any] = {
                "step": state.total_turns,
                "gen_ai.agent.name": meta.get("name", sa_id),
                "avp.subagent.invocation_id": invocation_id,
                "duration_ms": outcome.duration_ms,
                "avp.subagent.error": outcome.error,
            }
            if outcome.error_code is not None:
                failed_data["avp.subagent.error.code"] = outcome.error_code
            self._emit(
                SubagentFailedEvent(
                    subject=commission.run_id,
                    data=SubagentFailedData(
                        **self._shared_span(frame_span_id, self._current_turn_span_id),
                        **failed_data,
                    ),
                )
            )
            self._history.append(
                {
                    "role": "tool",
                    "tool": sa_id,
                    "call_id": tc.call_id,
                    "output": f"Error: {outcome.error}",
                }
            )
            return

        returned_data: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.agent.name": meta.get("name", sa_id),
            "avp.subagent.invocation_id": invocation_id,
            "duration_ms": outcome.duration_ms,
            "avp.subagent.result.text": outcome.text,
            "avp.subagent.reason": outcome.reason,
            "avp.subagent.usage": child_usage,
        }
        if outcome.structured is not None:
            returned_data["avp.subagent.result.structured"] = outcome.structured
        self._emit(
            SubagentReturnedEvent(
                subject=commission.run_id,
                data=SubagentReturnedData(
                    **self._shared_span(frame_span_id, self._current_turn_span_id),
                    **returned_data,
                ),
            )
        )
        self._history.append(
            {
                "role": "tool",
                "tool": sa_id,
                "call_id": tc.call_id,
                "output": outcome.text,
            }
        )

    def _emit_subagent_invoked_then_failed(
        self,
        *,
        tc,
        state: _MutableState,
        meta: dict[str, Any],
        invocation_id: str,
        frame_span_id: str,
        error: str,
        error_code: str,
        duration_ms: int,
        child_run_id: str | None,
    ) -> None:
        """Emit subagent_invoked + subagent_failed when the resolver call
        itself raised (no child run was spawned). The `subagent_invoked`
        event opens the frame even though the child never started so
        consumers see the lifecycle they expect; `subagent_failed` closes
        it with the resolver-side error."""
        commission = self.commission
        sa_id = tc.tool
        invoked_data: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.agent.name": meta.get("name", sa_id),
            "avp.subagent.invocation_id": invocation_id,
            "avp.subagent.input": dict(tc.input or {}),
        }
        if child_run_id is not None:
            invoked_data["avp.subagent.run_id"] = child_run_id
        description = meta.get("description")
        if description:
            invoked_data["gen_ai.agent.description"] = description
        self._emit(
            SubagentInvokedEvent(
                subject=commission.run_id,
                data=SubagentInvokedData(
                    **self._shared_span(frame_span_id, self._current_turn_span_id),
                    **invoked_data,
                ),
            )
        )
        failed_data: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.agent.name": meta.get("name", sa_id),
            "avp.subagent.invocation_id": invocation_id,
            "duration_ms": duration_ms,
            "avp.subagent.error": error,
            "avp.subagent.error.code": error_code,
        }
        self._emit(
            SubagentFailedEvent(
                subject=commission.run_id,
                data=SubagentFailedData(
                    **self._shared_span(frame_span_id, self._current_turn_span_id),
                    **failed_data,
                ),
            )
        )
        self._history.append(
            {
                "role": "tool",
                "tool": sa_id,
                "call_id": tc.call_id,
                "output": f"Error: {error}",
            }
        )

    # ── Prelude / footer ────────────────────────────────────────────────────

    def _emit_run_prelude(self) -> None:
        if self._descriptor is None:
            return
        commission = self.commission
        sup = commission.supervisor
        commission_snapshot = commission.model_dump(by_alias=True, exclude_none=True, mode="json")
        run_requested_kwargs: dict[str, Any] = {
            "avp.supervisor.name": sup.name if sup is not None else "unknown",
            "avp.commission": commission_snapshot,
        }
        if sup is not None and sup.version is not None:
            run_requested_kwargs["avp.supervisor.version"] = sup.version
        self._emit(
            RunRequestedEvent(
                subject=commission.run_id,
                data=RunRequestedData(
                    trace_id=self._trace_id,
                    span_id=new_span_id(),
                    parent_span_id=ZERO_SPAN_ID,
                    **run_requested_kwargs,
                ),
            )
        )
        self._emit(
            AgentDescribedEvent(
                subject=commission.run_id,
                data=AgentDescribedData(
                    trace_id=self._trace_id,
                    span_id=new_span_id(),
                    parent_span_id=ZERO_SPAN_ID,
                    **{"avp.descriptor": self._descriptor},
                ),
            )
        )

    def _build_tool_decls(self) -> list[dict[str, Any]] | None:
        """Effective built-in tool surface for `agent_started.data.tools`.
        Filtered by `Commission.enabled_builtin_tools` when set. MCP-server
        tools land on `mcp_server_connected.data.avp.mcp.tools` after
        resolution."""
        decls: list[dict[str, Any]] = []
        for bt in self._agent_builtin_tools:
            if not self._is_builtin_tool_enabled(bt["name"]):
                continue
            entry: dict[str, Any] = {"name": bt["name"]}
            if "description" in bt and bt["description"] is not None:
                entry["description"] = bt["description"]
            schema = bt.get("inputSchema") or bt.get("input_schema")
            if schema is not None:
                entry["inputSchema"] = schema
            entry["avp.dispatch_target"] = "local"
            decls.append(entry)
        return decls or None

    def _build_subagent_decls(self) -> list[dict[str, Any]] | None:
        """Subagent ids for `agent_started.data.subagents`. Emitted before
        resolution, so descriptions / schemas are not yet available;
        consumers correlate with `managed_ref_resolved` events to enrich.
        Honest-stub beats fabricated metadata."""
        commission = self.commission
        if not commission.subagents:
            return None
        return [{"name": sa.id} for sa in commission.subagents]

    def _build_skill_decls(self) -> list[dict[str, Any]] | None:
        commission = self.commission
        if not commission.skills:
            return None
        return [{"name": s.id} for s in commission.skills]

    def _emit_agent_started(self) -> None:
        commission = self.commission
        data_kwargs: dict[str, Any] = {
            "trace_id": self._trace_id,
            "span_id": self._agent_span_id,
            "parent_span_id": ZERO_SPAN_ID,
            "prompt": commission.prompt,
            "system_prompt": commission.system_prompt,
            "tools": self._build_tool_decls(),
            "skills": self._build_skill_decls(),
            "subagents": self._build_subagent_decls(),
        }
        if commission.model:
            data_kwargs["gen_ai.request.model"] = commission.model
        if commission.thread_id:
            data_kwargs["avp.thread_id"] = commission.thread_id
        if commission.tags:
            data_kwargs["avp.tags"] = commission.tags
        if commission.meta:
            data_kwargs["avp.meta"] = commission.meta

        self._emit(
            AgentStartedEvent(
                subject=commission.run_id,
                data=AgentStartedData(**data_kwargs),
            )
        )

    def _inject_skill_bodies_to_history(self) -> None:
        """Build the run's effective system prompt from
        `Commission.system_prompt` plus each resolved skill's content,
        then seed history with system + user-prompt messages.

        Skills with no `content` field in the resolved material are
        recorded but not injected (the resolver returned metadata-only).
        """
        commission = self.commission
        sys_parts: list[str] = []
        if commission.system_prompt:
            sys_parts.append(commission.system_prompt)
        for skill in commission.skills or []:
            material = self._resolved_skills.get(skill.id) or {}
            body = material.get("content")
            if body:
                sys_parts.append(f'<skill name="{skill.id}">\n{body}\n</skill>')
        if sys_parts:
            self._history.append({"role": "system", "content": "\n\n".join(sys_parts)})
        if commission.prompt:
            self._history.append({"role": "user", "content": commission.prompt})

    def _emit_skills_loaded(self) -> None:
        """One `skill_loaded` event per resolved skill whose body actually
        entered the agent's history (i.e., the resolver returned `content`).
        Honest-silent for metadata-only resolutions — the registration view
        is `agent_started.data.skills`."""
        commission = self.commission
        for skill in commission.skills or []:
            material = self._resolved_skills.get(skill.id) or {}
            if not material.get("content"):
                continue
            self._emit(
                SkillLoadedEvent(
                    subject=commission.run_id,
                    data=SkillLoadedData(
                        **self._own_span(self._agent_span_id),
                        step=0,
                        **{"avp.skill.name": skill.id},
                    ),
                )
            )

    def _emit_mcp_connections(self) -> None:
        """Emit `mcp_server_connected` for each resolved MCP server. v0.1's
        reference agent doesn't drive a real MCP handshake — it emits a
        stub event so supervisors can pin the lifecycle in tests today.
        Production agents that dial the resolved endpoint MUST populate
        `avp.mcp.tools[]` from MCP's `tools/list`."""
        commission = self.commission
        for server in commission.mcp_servers or []:
            self._emit(
                McpServerConnectedEvent(
                    subject=commission.run_id,
                    data=McpServerConnectedData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "avp.mcp.server_id": server.id,
                            "avp.mcp.protocol_version": MCP_PROTOCOL_VERSION,
                            "avp.mcp.tool_count": 0,
                        },
                    ),
                )
            )

    def _emit_mcp_disconnections(self, reason: str) -> None:
        commission = self.commission
        if not commission.mcp_servers:
            return
        # Disconnect only servers that actually connected (resolver may have
        # short-circuited before some entries were processed).
        for server in commission.mcp_servers:
            if server.id not in self._resolved_mcp_servers:
                continue
            self._emit(
                McpServerDisconnectedEvent(
                    subject=commission.run_id,
                    data=McpServerDisconnectedData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "avp.mcp.server_id": server.id,
                            "avp.mcp.disconnect_reason": reason,
                        },
                    ),
                )
            )

    def _emit_agent_stopped(self, reason: StopReason) -> AgentStoppedEvent:
        commission = self.commission
        self._emit_mcp_disconnections("clean")
        snap = self._state.snapshot(_monotonic_ms())
        ev = AgentStoppedEvent(
            subject=commission.run_id,
            data=AgentStoppedData(
                trace_id=self._trace_id,
                span_id=self._agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                **{
                    "avp.reason": reason,
                    "avp.state": snap,
                    "avp.total_tokens": snap.total_tokens,
                    "avp.total_cost_usd": snap.total_cost_usd,
                    "avp.total_turns": snap.total_turns,
                    "avp.duration_ms": snap.duration_ms,
                },
            ),
        )
        self._emit(ev)
        return ev


__all__ = ["AVPAgent"]
