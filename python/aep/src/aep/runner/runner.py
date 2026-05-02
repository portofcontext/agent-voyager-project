"""AEPRunner — the v0.1 normative loop.

The agent runs inside the supervisor's declared environment. Boundary, tools,
re_observation, verifiers all come from Config. The supervisor does not reach
in mid-run; the agent enforces declared rules and emits facts. Two RPC
interactions remain (tool_exec, re_observation supervisor-source); both are
agent-initiated calls into services the supervisor stood up at Config time.
"""

from __future__ import annotations

import itertools
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from aep.enums import OnFailure, StopReason
from aep.runner.boundary import (
    check_consumption,
    check_step_projection,
)
from aep.runner.drivers import (
    ModelDriver,
    SupervisorDriver,
    ToolDriver,
    ToolOutcome,
)
from aep.types import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Config,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    ReObservation,
    ReObservationInjectedEvent,
    ReObservationRequestEvent,
    ReObservationResolvedEvent,
    ReObservationSourceShell,
    ReObservationSourceSupervisor,
    ReObservationTimedOutEvent,
    RunStateSnapshot,
    SkillLoadedEvent,
    TextEmittedEvent,
    Tool,
    ToolExecRequestEvent,
    ToolExecResolvedEvent,
    ToolExecTimedOutEvent,
    ToolFailedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    Verifier,
    VerifierEvaluatedEvent,
    now_iso,
)

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


# ── The runner ────────────────────────────────────────────────────────────────


class _VerifierHalt(Exception):
    """Raised internally when a verifier with on_failure=halt fails."""


class AEPRunner:
    """Reference AEP runner. v0.1 model: declarative environment, no mid-run reach-in."""

    def __init__(
        self,
        config: Config,
        model: ModelDriver,
        tools: ToolDriver,
        supervisor: SupervisorDriver,
    ) -> None:
        self.config = config
        self.model = model
        self.tools = tools
        self.supervisor = supervisor
        self.trajectory: list[BaseModel | dict[str, Any]] = []
        self._history: list[dict[str, Any]] = []
        self._supervisor_tools_by_name: dict[str, Tool] = {t.name: t for t in (config.tools or [])}
        self._req_seq = itertools.count(1)
        self._next_request_id = lambda: f"req-{next(self._req_seq)}"

    # ── Emission ────────────────────────────────────────────────────────────

    def _emit(self, event: BaseModel) -> None:
        self.trajectory.append(event)
        self.supervisor.observe(event)

    # ── Run lifecycle ───────────────────────────────────────────────────────

    def run(self) -> AgentStoppedEvent:
        state = _MutableState(
            started_at=now_iso(),
            started_monotonic_ms=_monotonic_ms(),
        )
        self._state = state

        self._emit_agent_started()
        self._emit_skills_loaded()

        try:
            self._run_verifiers_for("before_first_turn")
            self._main_loop()
        except _VerifierHalt:
            return self._emit_agent_stopped(StopReason.verifier_failed)

        for ev in reversed(self.trajectory):
            if isinstance(ev, AgentStoppedEvent):
                return ev
        raise RuntimeError("AEPRunner: trajectory missing agent_stopped — invariant violation")

    # ── Main loop ───────────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        state = self._state
        cfg = self.config

        while True:
            decision = check_step_projection(state.snapshot(_monotonic_ms()), cfg.boundary)
            if decision.stop:
                self._run_verifiers_for("at_end")
                self._emit_agent_stopped(decision.reason or StopReason.turn_limit)
                return

            upcoming = state.total_turns + 1
            self._run_re_observations(upcoming)
            self._run_verifiers_for("before_each_turn")

            state.total_turns += 1
            self._emit(
                ModelTurnStartedEvent(
                    run_id=cfg.run_id,
                    step=state.total_turns,
                    context_messages=len(self._history),
                )
            )
            response = self.model.step(self._history)
            self._emit(
                ModelTurnEndedEvent(
                    run_id=cfg.run_id,
                    step=state.total_turns,
                    tokens_input=response.tokens_input,
                    tokens_output=response.tokens_output,
                    cost_usd=response.cost_usd,
                    duration_ms=response.duration_ms,
                    tokens_cache_read=response.tokens_cache_read,
                    tokens_cache_write=response.tokens_cache_write,
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
                    run_id=cfg.run_id,
                    state=state.snapshot(_monotonic_ms()),
                )
            )

            decision = check_consumption(state.snapshot(_monotonic_ms()), cfg.boundary)
            if decision.stop:
                self._run_verifiers_for("at_end")
                self._emit_agent_stopped(decision.reason or StopReason.budget_exhausted)
                return

            if response.text:
                self._emit(
                    TextEmittedEvent(
                        run_id=cfg.run_id,
                        step=state.total_turns,
                        text=response.text,
                    )
                )
                self._history.append({"role": "assistant", "content": response.text})

            for tc in response.tool_calls:
                self._handle_tool_call(tc, state)
                decision = check_consumption(state.snapshot(_monotonic_ms()), cfg.boundary)
                if decision.stop:
                    self._run_verifiers_for("at_end")
                    self._emit_agent_stopped(decision.reason or StopReason.budget_exhausted)
                    return
                self._run_verifiers_for(f"on_tool:{tc.tool}")

            self._run_verifiers_for("after_each_turn")

            if response.converged:
                self._run_verifiers_for("at_end")
                self._emit_agent_stopped(StopReason.converged)
                return

    # ── Tool handling ────────────────────────────────────────────────────────

    def _handle_tool_call(self, tc, state: _MutableState) -> None:
        cfg = self.config
        self._emit(
            ToolInvokedEvent(
                run_id=cfg.run_id,
                step=state.total_turns,
                call_id=tc.call_id,
                tool=tc.tool,
                input=tc.input,
            )
        )
        state.tools_invoked[tc.tool] = state.tools_invoked.get(tc.tool, 0) + 1

        if tc.tool in self._supervisor_tools_by_name:
            self._handle_rpc_tool(tc, state)
            return

        if not self.tools.is_local(tc.tool):
            self._emit(
                ToolFailedEvent(
                    run_id=cfg.run_id,
                    step=state.total_turns,
                    call_id=tc.call_id,
                    tool=tc.tool,
                    error=f"unknown tool {tc.tool!r}",
                )
            )
            return

        outcome: ToolOutcome = self.tools.invoke(tc.tool, tc.input)
        if outcome.error is not None and not outcome.rejected:
            self._emit(
                ToolFailedEvent(
                    run_id=cfg.run_id,
                    step=state.total_turns,
                    call_id=tc.call_id,
                    tool=tc.tool,
                    error=outcome.error,
                )
            )
            return

        out_str = outcome.output if outcome.output is not None else ""
        self._emit(
            ToolReturnedEvent(
                run_id=cfg.run_id,
                step=state.total_turns,
                call_id=tc.call_id,
                tool=tc.tool,
                output=out_str,
                output_json=outcome.output_json,
                duration_ms=outcome.duration_ms,
                rejected=outcome.rejected if outcome.rejected else None,
                rejection_reason=outcome.rejection_reason,
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

    def _handle_rpc_tool(self, tc, state: _MutableState) -> None:
        cfg = self.config
        tool_decl = self._supervisor_tools_by_name[tc.tool]
        request_id = self._next_request_id()
        self._emit(
            ToolExecRequestEvent(
                run_id=cfg.run_id,
                step=state.total_turns,
                request_id=request_id,
                call_id=tc.call_id,
                tool=tc.tool,
                input=tc.input,
                timeout_ms=tool_decl.timeout_ms,
            )
        )

        msg = self.supervisor.get_tool_exec_response(request_id, tool_decl.timeout_ms)
        if msg is None:
            self._emit(
                ToolExecTimedOutEvent(
                    run_id=cfg.run_id,
                    step=state.total_turns,
                    request_id=request_id,
                    call_id=tc.call_id,
                    tool=tc.tool,
                )
            )
            output = ""
        else:
            assert isinstance(msg, ToolExecResolvedEvent)
            self._emit(msg)
            if msg.error:
                output = f"Error: {msg.output}" if msg.output else f"Error: {msg.error}"
            else:
                output = msg.output

        self._emit(
            ToolReturnedEvent(
                run_id=cfg.run_id,
                step=state.total_turns,
                call_id=tc.call_id,
                tool=tc.tool,
                output=output,
                output_json=msg.output_json if isinstance(msg, ToolExecResolvedEvent) else None,
                duration_ms=1,
            )
        )
        self._history.append(
            {
                "role": "tool",
                "tool": tc.tool,
                "call_id": tc.call_id,
                "output": output,
            }
        )

    # ── Verifier handling ──────────────────────────────────────────────────

    def _run_verifiers_for(self, trigger: str) -> None:
        cfg = self.config
        if not cfg.verifiers:
            return
        for verifier in cfg.verifiers:
            if verifier.trigger != trigger:
                continue
            self._run_verifier(verifier)

    def _run_verifier(self, verifier: Verifier) -> None:
        passed, data = self._execute_verifier(verifier)
        cfg = self.config
        self._emit(
            VerifierEvaluatedEvent(
                run_id=cfg.run_id,
                name=verifier.name,
                passed=passed,
                step=self._state.total_turns or None,
                data=data,
            )
        )
        if passed:
            return
        self._apply_on_failure(verifier)

    def _execute_verifier(self, verifier: Verifier) -> tuple[bool, dict[str, Any] | None]:
        """Execute a verifier source. Returns (passed, optional data dict)."""
        src = verifier.source
        # v0.1 only ships shell-source verifiers
        try:
            result = subprocess.run(
                ["sh", "-c", src.shell],
                capture_output=True,
                text=True,
                check=False,
                timeout=verifier.timeout_ms / 1000.0,
            )
        except subprocess.TimeoutExpired:
            return False, {"error": "verifier timeout", "timeout_ms": verifier.timeout_ms}
        passed = result.returncode == 0
        data: dict[str, Any] = {
            "command": src.shell,
            "exit_code": result.returncode,
        }
        # Trim outputs to keep trajectory small.
        if result.stdout:
            data["stdout"] = result.stdout[:2000]
        if result.stderr:
            data["stderr"] = result.stderr[:2000]
        return passed, data

    def _apply_on_failure(self, verifier: Verifier) -> None:
        if verifier.on_failure == OnFailure.continue_:
            return
        if verifier.on_failure == OnFailure.halt:
            raise _VerifierHalt()
        if verifier.on_failure == OnFailure.inject_correction:
            assert verifier.correction_message is not None
            self._history.append(
                {
                    "role": "user",
                    "content": verifier.correction_message,
                    "kind": "correction",
                    "verifier_name": verifier.name,
                }
            )
            return
        raise ValueError(f"unknown on_failure {verifier.on_failure!r}")

    # ── Re-observation handling ────────────────────────────────────────────

    def _run_re_observations(self, upcoming_turn: int) -> None:
        cfg = self.config
        if not cfg.re_observation:
            return
        for entry in cfg.re_observation:
            if not self._re_obs_should_fire(entry, upcoming_turn):
                continue
            self._fire_re_observation(entry, upcoming_turn)

    @staticmethod
    def _re_obs_should_fire(entry: ReObservation, upcoming_turn: int) -> bool:
        if entry.trigger == "before_each_turn":
            return True
        if entry.trigger == "before_first_turn":
            return upcoming_turn == 1
        if entry.trigger == "every_n_turns":
            n = entry.every_n or 1
            return (upcoming_turn - 1) % n == 0
        return False

    def _fire_re_observation(self, entry: ReObservation, upcoming_turn: int) -> None:
        cfg = self.config
        if isinstance(entry.source, ReObservationSourceShell):
            content = self._fetch_shell_observation(entry.source.shell)
            self._inject_observation(
                entry, content, source_kind="shell", upcoming_turn=upcoming_turn
            )
            return
        assert isinstance(entry.source, ReObservationSourceSupervisor)
        request_id = self._next_request_id()
        self._emit(
            ReObservationRequestEvent(
                run_id=cfg.run_id,
                step=upcoming_turn,
                request_id=request_id,
                name=entry.name,
                timeout_ms=entry.timeout_ms,
            )
        )
        msg = self.supervisor.get_re_observation_response(request_id, entry.timeout_ms)
        if msg is None:
            self._emit(
                ReObservationTimedOutEvent(
                    run_id=cfg.run_id,
                    step=upcoming_turn,
                    request_id=request_id,
                    name=entry.name,
                )
            )
            return
        assert isinstance(msg, ReObservationResolvedEvent)
        self._emit(msg)
        self._inject_observation(
            entry,
            msg.content,
            source_kind="supervisor",
            upcoming_turn=upcoming_turn,
        )

    def _fetch_shell_observation(self, command: str) -> str:
        result = subprocess.run(
            ["sh", "-c", command],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout

    def _inject_observation(
        self,
        entry: ReObservation,
        content: str,
        *,
        source_kind: str,
        upcoming_turn: int,
    ) -> None:
        original_size = len(content)
        injected = content
        truncated = False
        if entry.max_tokens is not None and original_size > entry.max_tokens:
            injected = content[: entry.max_tokens]
            truncated = True
        injected_size = len(injected)
        preview = injected[:200]

        cfg = self.config
        self._emit(
            ReObservationInjectedEvent(
                run_id=cfg.run_id,
                step=upcoming_turn,
                name=entry.name,
                trigger=entry.trigger,
                source_kind=source_kind,  # type: ignore[arg-type]
                content_preview=preview,
                injected_size=injected_size,
                original_size=original_size if truncated else None,
                truncated=True if truncated else None,
            )
        )
        self._history.append(
            {
                "role": "user",
                "content": injected,
                "kind": "observation",
                "observation_name": entry.name,
            }
        )

    # ── First / last events ─────────────────────────────────────────────────

    def _emit_agent_started(self) -> None:
        cfg = self.config
        tools_meta = None
        if cfg.tools:
            tools_meta = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in cfg.tools
            ]
        skills_meta = [s.name for s in (cfg.skills or [])] or None
        self._emit(
            AgentStartedEvent(
                run_id=cfg.run_id,
                model=cfg.model or "unspecified",
                prompt=cfg.prompt,
                system_prompt=cfg.system_prompt,
                tools=tools_meta,
                skills=skills_meta,
                thread_id=cfg.thread_id,
                tags=cfg.tags,
                meta=cfg.meta,
            )
        )
        if cfg.system_prompt:
            self._history.append({"role": "system", "content": cfg.system_prompt})
        if cfg.prompt:
            self._history.append({"role": "user", "content": cfg.prompt})

    def _emit_skills_loaded(self) -> None:
        cfg = self.config
        if not cfg.skills:
            return
        for skill in cfg.skills:
            self._emit(
                SkillLoadedEvent(
                    run_id=cfg.run_id,
                    step=0,
                    name=skill.name,
                    skill_source=skill.source,
                )
            )

    def _emit_agent_stopped(self, reason: StopReason) -> AgentStoppedEvent:
        cfg = self.config
        snap = self._state.snapshot(_monotonic_ms())
        ev = AgentStoppedEvent(
            run_id=cfg.run_id,
            reason=reason,
            state=snap,
            total_tokens=snap.total_tokens,
            total_cost_usd=snap.total_cost_usd,
            total_turns=snap.total_turns,
            duration_ms=snap.duration_ms,
        )
        self._emit(ev)
        return ev


__all__ = ["AEPRunner"]
