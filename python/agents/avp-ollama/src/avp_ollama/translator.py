"""OllamaTranslator — drives one AVP run against Ollama, emits a
conforming trajectory to the supervisor.

Scope (see package README): single chat loop, no tool use, no managed
assets. Honors `RESCUE_FAIL_AT` for the rescue demo.
"""

from __future__ import annotations

import logging
import os
import random
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from .supervisor_client import SupervisorEventClient

logger = logging.getLogger(__name__)

# AVP event-type constants, mirroring `avp.types`. We hand-roll the
# CloudEvents envelopes here to avoid a hard dep on the full `avp`
# package's pydantic models at runtime; the supervisor + the AVP test
# suite are the canonical validators.
_T_RUN_REQUESTED = "avp.run_requested"
_T_AGENT_DESCRIBED = "avp.agent_described"
_T_AGENT_STARTED = "avp.agent_started"
_T_AGENT_STOPPED = "avp.agent_stopped"
_T_MODEL_TURN_STARTED = "avp.model_turn_started"
_T_MODEL_TURN_ENDED = "avp.model_turn_ended"
_T_TEXT_EMITTED = "avp.text_emitted"
_T_COST_RECORDED = "avp.cost_recorded"
_T_ERROR_OCCURRED = "avp.error_occurred"

_SOURCE_AGENT = "avp://agent"
_SOURCE_SUPERVISOR = "avp://supervisor"

# Default backend identity stamped onto `avp.runner` in every emitted
# event. Override via `AVP_RUNNER_BACKEND` env var when launching the
# runner — e.g., the rescue demo's secondary runner sets
# `AVP_RUNNER_BACKEND=local-ollama-2` so its events attribute correctly.
_DEFAULT_BACKEND_IDENTITY = "local-ollama"
_AGENT_NAME = "avp-ollama"
_AGENT_VERSION = "0.1.0"
_AVP_SPEC_VERSION = "0.1"
_ZERO_SPAN = "0" * 16
_ZERO_TRACE = "0" * 32


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_event_id() -> str:
    return str(uuid.uuid4())


def _new_trace_id() -> str:
    return secrets.token_hex(16)


def _new_span_id() -> str:
    return secrets.token_hex(8)


@dataclass
class RescueFailAt:
    """Parsed `RESCUE_FAIL_AT` directive. See package README for the env
    spec. `none` means no injected failure."""

    mode: str = "none"  # one of: "none", "now", "turn", "prob"
    turn: int = 0
    probability: float = 0.0

    @classmethod
    def from_env(cls, raw: str | None = None) -> "RescueFailAt":
        if raw is None:
            raw = os.environ.get("RESCUE_FAIL_AT")
        if not raw:
            return cls()
        raw = raw.strip().lower()
        if raw == "now":
            return cls(mode="now")
        if raw.startswith("turn:"):
            try:
                n = int(raw.split(":", 1)[1])
                if n >= 1:
                    return cls(mode="turn", turn=n)
            except ValueError:
                pass
        if raw.startswith("prob:"):
            try:
                p = float(raw.split(":", 1)[1])
                if 0.0 <= p <= 1.0:
                    return cls(mode="prob", probability=p)
            except ValueError:
                pass
        logger.warning("RESCUE_FAIL_AT=%r unrecognized; ignoring", raw)
        return cls()

    def fire_before_turn(self, turn_index: int) -> bool:
        """Returns True iff a failure should be injected before turn N
        (1-indexed). `now` mode is handled separately (pre-turn-loop)."""
        if self.mode == "turn":
            return turn_index == self.turn
        if self.mode == "prob":
            return random.random() < self.probability
        return False


@dataclass
class _RunState:
    run_id: str
    seq: int = 0
    trace_id: str = field(default_factory=_new_trace_id)
    agent_span_id: str = field(default_factory=_new_span_id)
    total_turns: int = 0
    total_tokens: int = 0
    started_at: float = field(default_factory=time.time)


class _InjectedFailure(Exception):
    """Sentinel raised by the translator when `RESCUE_FAIL_AT` fires."""


class OllamaTranslator:
    """One translator per run. Stateful: tracks seq, span ids,
    accumulated cost/tokens."""

    def __init__(
        self,
        run_id: str,
        config: dict[str, Any],
        *,
        client: SupervisorEventClient | None = None,
        ollama_host: str | None = None,
        model_default: str | None = None,
        max_turns: int | None = None,
        force_turns: int | None = None,
        continuation_prompt: str | None = None,
        rescue_fail_at: RescueFailAt | None = None,
    ) -> None:
        self.run_id = run_id
        self.config = config
        self.client = client or SupervisorEventClient()
        self.ollama_host = (
            ollama_host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
        ).rstrip("/")
        self.model = (
            config.get("model")
            or model_default
            or os.environ.get("OLLAMA_MODEL_DEFAULT")
            or "llama3.2:3b"
        )
        self.max_turns = int(max_turns or os.environ.get("OLLAMA_MAX_TURNS") or 8)
        # When set (>0), drive the conversation for exactly this many
        # turns regardless of whether Ollama signaled `done`. Between
        # turns the translator appends a synthetic user-role
        # continuation message to keep the model generating. This is
        # what makes RESCUE_FAIL_AT=turn:N fire on a *real* turn-N
        # boundary instead of the short-prompt fall-through.
        # `0` / unset = original behavior (exit when model is done).
        env_force = os.environ.get("OLLAMA_FORCE_TURNS")
        self.force_turns = int(force_turns if force_turns is not None else (env_force or 0))
        self.continuation_prompt = (
            continuation_prompt
            or os.environ.get("OLLAMA_CONTINUATION_PROMPT")
            or "Continue with the next step. Be brief."
        )
        self.backend_identity = (
            os.environ.get("AVP_RUNNER_BACKEND") or _DEFAULT_BACKEND_IDENTITY
        )
        self.rescue_fail_at = rescue_fail_at or RescueFailAt.from_env()
        self.state = _RunState(run_id=run_id)
        self._http = httpx.Client(timeout=120.0)

    # ── public driver ────────────────────────────────────────────────────

    def run(self) -> str:
        """Drive the run to completion (or injected failure). Returns the
        terminal reason (`converged`, `error`) or `execution_backend_failure`
        when the rescue path was triggered."""
        try:
            # Discover where to start emitting. When a run was rescued
            # from another backend, the supervisor already has the
            # original prelude + the avp.run_rescued bracket persisted.
            # Picking next_seq from the supervisor avoids seq-collision
            # 409s on every event we'd otherwise emit at seq=0..N.
            try:
                start_seq = self.client.next_seq(self.run_id)
            except httpx.HTTPError as e:
                logger.warning("next_seq lookup failed (%s); starting at 0", e)
                start_seq = 0
            self.state.seq = start_seq
            is_rescued = start_seq > 0
            if is_rescued:
                logger.info(
                    "rescued continuation: starting at seq=%d (skipping prelude)",
                    start_seq,
                )
                # Inherit the original `agent_started` span_id from the
                # prior runner so the span tree stays continuous per
                # AVP §7.3. Best-effort — if the lookup fails, we fall
                # back to a fresh span; the bracket event still makes
                # the swap observable.
                self._inherit_agent_span()
            else:
                self._emit_prelude()
            if self.rescue_fail_at.mode == "now":
                self._inject_failure("RESCUE_FAIL_AT=now: failing after prelude")
            messages = self._initial_messages()
            last_turn = 0
            # When force_turns is set, run exactly that many turns
            # ignoring Ollama's `done` flag (and inject a continuation
            # user-message between turns to keep the model generating).
            # Otherwise run up to max_turns, exiting on `done` as
            # normal.
            turn_ceiling = (
                self.force_turns if self.force_turns > 0 else self.max_turns
            )
            for turn_index in range(1, turn_ceiling + 1):
                if self.rescue_fail_at.fire_before_turn(turn_index):
                    self._inject_failure(
                        f"RESCUE_FAIL_AT={self.rescue_fail_at.mode}: failing before turn {turn_index}"
                    )
                done, assistant = self._run_turn(turn_index, messages)
                last_turn = turn_index
                if assistant:
                    messages.append({"role": "assistant", "content": assistant})
                if self.force_turns > 0:
                    # Keep the chat going: prompt the model to continue.
                    # Only inject the continuation if we have more turns
                    # to go, to avoid a dangling user message after the
                    # last assistant reply.
                    if turn_index < turn_ceiling:
                        messages.append(
                            {"role": "user", "content": self.continuation_prompt}
                        )
                elif done:
                    break

            # The loop ended. If RESCUE_FAIL_AT=turn:N specified a turn
            # we never reached (typical with short prompts and
            # force_turns unset), fire the failure here instead of
            # silently finishing — so RESCUE_FAIL_AT acts as a
            # demo-wants-a-failure directive even in the
            # converge-on-turn-1 case.
            if (
                self.rescue_fail_at.mode == "turn"
                and self.rescue_fail_at.turn > last_turn
            ):
                self._inject_failure(
                    f"RESCUE_FAIL_AT=turn:{self.rescue_fail_at.turn} but converged at turn {last_turn} "
                    f"— failing before agent_stopped"
                )

            self._emit_agent_stopped("converged")
            return "converged"
        except _InjectedFailure:
            return "execution_backend_failure"
        except Exception as exc:
            logger.exception("OllamaTranslator unhandled error")
            self._emit_error(code="agent_crash", message=str(exc), span_id=self.state.agent_span_id)
            self._emit_agent_stopped("error", message=str(exc))
            return "error"
        finally:
            self._http.close()

    # ── event emission ───────────────────────────────────────────────────

    def _next_seq(self) -> int:
        s = self.state.seq
        self.state.seq += 1
        return s

    def _envelope(
        self,
        type_: str,
        data: dict[str, Any],
        *,
        source: str = _SOURCE_AGENT,
    ) -> dict[str, Any]:
        return {
            "specversion": "1.0",
            "id": _new_event_id(),
            "type": type_,
            "source": source,
            "subject": self.run_id,
            "time": _now_iso(),
            "datacontenttype": "application/json",
            "data": data,
        }

    def _runner_attribution(self) -> dict[str, Any]:
        return {"backend": self.backend_identity, "model": self.model}

    def _post(self, event: dict[str, Any]) -> None:
        seq = self._next_seq()
        try:
            self.client.append_event(self.run_id, seq, event)
        except httpx.HTTPError as e:
            logger.warning("event post failed (seq=%d, type=%s): %s", seq, event.get("type"), e)

    def _inherit_agent_span(self) -> None:
        """Look up the original `agent_started` event the prior runner
        emitted and copy its trace_id / span_id onto our run state so
        subsequent events nest under the same agent span. Best-effort:
        if the prior trajectory is unreadable or doesn't have an
        `agent_started`, fall back to the freshly-generated ids
        (consumers can still attribute via the `avp.runner` field and
        the `avp.run_rescued` bracket)."""
        try:
            events = self.client.fetch_events(self.run_id)
        except httpx.HTTPError as e:
            logger.warning("fetch_events for span inherit failed: %s", e)
            return
        for row in events:
            envelope = row.get("event") or {}
            if envelope.get("type") != _T_AGENT_STARTED:
                continue
            data = envelope.get("data") or {}
            trace = data.get("trace_id")
            span = data.get("span_id")
            if isinstance(trace, str) and isinstance(span, str):
                self.state.trace_id = trace
                self.state.agent_span_id = span
                logger.info(
                    "inherited agent span (trace=%s, span=%s)", trace, span
                )
            return

    def _emit_prelude(self) -> None:
        # 1. run_requested (supervisor-attributed, agent-relayed)
        commission_supervisor = self.config.get("supervisor") or {}
        sup_name = commission_supervisor.get("name") if isinstance(commission_supervisor, dict) else None
        sup_version = (
            commission_supervisor.get("version") if isinstance(commission_supervisor, dict) else None
        )
        self._post(
            self._envelope(
                _T_RUN_REQUESTED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": _new_span_id(),
                    "parent_span_id": _ZERO_SPAN,
                    "avp.commission": self.config,
                    "avp.supervisor.name": sup_name or "unknown",
                    **({"avp.supervisor.version": sup_version} if sup_version else {}),
                },
                source=_SOURCE_SUPERVISOR,
            )
        )

        # 2. agent_described
        descriptor = {
            "name": _AGENT_NAME,
            "version": _AGENT_VERSION,
            "avp_spec_version": _AVP_SPEC_VERSION,
            "model": self.model,
            "ollama_host": self.ollama_host,
            "tools": [],
            "subagents": [],
            "skills": [],
        }
        self._post(
            self._envelope(
                _T_AGENT_DESCRIBED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": _new_span_id(),
                    "parent_span_id": _ZERO_SPAN,
                    "avp.descriptor": descriptor,
                    "avp.runner": self._runner_attribution(),
                },
            )
        )

        # 3. agent_started (opens the agent span)
        prompt = self.config.get("prompt", "")
        self._post(
            self._envelope(
                _T_AGENT_STARTED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": self.state.agent_span_id,
                    "parent_span_id": _ZERO_SPAN,
                    "prompt": prompt,
                    "model": self.model,
                    "tools": [],
                    "subagents": [],
                    "skills": [],
                    "mcp_servers": [],
                    "avp.runner": self._runner_attribution(),
                },
            )
        )

    def _run_turn(
        self, turn_index: int, messages: list[dict[str, str]]
    ) -> tuple[bool, str]:
        """Run one model turn. Returns `(done, assistant_text)`."""
        turn_span = _new_span_id()
        self._post(
            self._envelope(
                _T_MODEL_TURN_STARTED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": turn_span,
                    "parent_span_id": self.state.agent_span_id,
                    "turn": turn_index,
                    "model": self.model,
                    "avp.runner": self._runner_attribution(),
                },
            )
        )

        # Call Ollama.
        body = {"model": self.model, "messages": messages, "stream": False}
        try:
            resp = self._http.post(f"{self.ollama_host}/api/chat", json=body)
            resp.raise_for_status()
            response = resp.json()
        except httpx.HTTPError as e:
            # Ollama is part of the *execution backend* (this runner's
            # host environment). A transport failure to Ollama is a
            # runner-environment failure, not an agent-side error.
            # Signal it as `execution_backend_failure` so the supervisor
            # can rescue.
            self._emit_error(
                code="execution_backend_failure",
                message=f"ollama transport: {e}",
                span_id=turn_span,
            )
            raise _InjectedFailure() from e

        assistant = (response.get("message") or {}).get("content") or ""
        prompt_tokens = int(response.get("prompt_eval_count") or 0)
        eval_tokens = int(response.get("eval_count") or 0)
        turn_tokens = prompt_tokens + eval_tokens
        self.state.total_turns += 1
        self.state.total_tokens += turn_tokens

        self._post(
            self._envelope(
                _T_MODEL_TURN_ENDED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": turn_span,
                    "parent_span_id": self.state.agent_span_id,
                    "turn": turn_index,
                    "model": self.model,
                    "gen_ai.usage.input_tokens": prompt_tokens,
                    "gen_ai.usage.output_tokens": eval_tokens,
                    "avp.runner": self._runner_attribution(),
                },
            )
        )

        if assistant:
            self._post(
                self._envelope(
                    _T_TEXT_EMITTED,
                    {
                        "trace_id": self.state.trace_id,
                        "span_id": _new_span_id(),
                        "parent_span_id": turn_span,
                        "text": assistant,
                        "avp.runner": self._runner_attribution(),
                    },
                )
            )

        self._emit_cost(turn_span)

        # Heuristic: Ollama's non-streaming /api/chat returns done=true
        # on the final message; we always get one assistant message per
        # call so we treat each turn as "done" for the demo. A real
        # multi-turn loop would feed the assistant message back and
        # decide based on tool use or model-emitted stop signals.
        done = bool(response.get("done", True))
        return done, assistant

    def _emit_cost(self, parent_span: str) -> None:
        self._post(
            self._envelope(
                _T_COST_RECORDED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": _new_span_id(),
                    "parent_span_id": parent_span,
                    "avp.state": {
                        "total_turns": self.state.total_turns,
                        "total_tokens": self.state.total_tokens,
                        "total_cost_usd": 0.0,
                    },
                    "avp.runner": self._runner_attribution(),
                },
            )
        )

    def _emit_agent_stopped(self, reason: str, message: str | None = None) -> None:
        data: dict[str, Any] = {
            "trace_id": self.state.trace_id,
            "span_id": self.state.agent_span_id,
            "parent_span_id": _ZERO_SPAN,
            "avp.reason": reason,
            "avp.total_turns": self.state.total_turns,
            "avp.total_tokens": self.state.total_tokens,
            "avp.total_cost_usd": 0.0,
            "avp.duration_ms": int((time.time() - self.state.started_at) * 1000),
            "avp.state": {
                "total_turns": self.state.total_turns,
                "total_tokens": self.state.total_tokens,
                "total_cost_usd": 0.0,
            },
            "avp.runner": self._runner_attribution(),
        }
        if message:
            data["avp.error.message"] = message
        self._post(self._envelope(_T_AGENT_STOPPED, data))

    def _emit_error(self, *, code: str, message: str, span_id: str) -> None:
        self._post(
            self._envelope(
                _T_ERROR_OCCURRED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": _new_span_id(),
                    "parent_span_id": span_id,
                    "avp.error.code": code,
                    "avp.error.message": message,
                    "avp.runner": self._runner_attribution(),
                },
            )
        )

    def _inject_failure(self, message: str) -> None:
        """Emit `execution_backend_failure` and bail out. Deliberately
        does **not** emit `agent_stopped` — leaves the run mid-flight so
        the supervisor's rescue path takes over."""
        logger.info("RESCUE_FAIL_AT triggered: %s", message)
        self._emit_error(
            code="execution_backend_failure",
            message=message,
            span_id=self.state.agent_span_id,
        )
        raise _InjectedFailure(message)

    def _initial_messages(self) -> list[dict[str, str]]:
        prompt = self.config.get("prompt", "")
        system = self.config.get("system_prompt")
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        if prompt:
            msgs.append({"role": "user", "content": prompt})
        return msgs
