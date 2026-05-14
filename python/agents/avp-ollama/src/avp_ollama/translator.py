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
_T_TOOL_INVOKED = "avp.tool_invoked"
_T_TOOL_RETURNED = "avp.tool_returned"
_T_TOOL_FAILED = "avp.tool_failed"

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


@dataclass
class InjectUserMessageAt:
    """Parsed `OLLAMA_INJECT_USER_MESSAGE_AT` directive. Spec:
    `turn:N:content` — inject `{role: user, content}` into the
    conversation **after** turn N completes and **before** turn N+1
    runs. Demo / test instrumentation used to simulate a user replying
    mid-conversation; mainly used by the warm-rescue T2 smoke to
    introduce a recall-token into the chat history."""

    turn: int = 0
    content: str = ""

    @classmethod
    def from_env(cls, raw: str | None = None) -> "InjectUserMessageAt":
        if raw is None:
            raw = os.environ.get("OLLAMA_INJECT_USER_MESSAGE_AT")
        if not raw:
            return cls()
        # `turn:N:content` — content may itself contain colons; only
        # split on the first two.
        prefix = "turn:"
        if not raw.startswith(prefix):
            logger.warning("OLLAMA_INJECT_USER_MESSAGE_AT=%r unrecognized; ignoring", raw)
            return cls()
        rest = raw[len(prefix):]
        if ":" not in rest:
            logger.warning("OLLAMA_INJECT_USER_MESSAGE_AT=%r missing content; ignoring", raw)
            return cls()
        n_str, content = rest.split(":", 1)
        try:
            n = int(n_str)
        except ValueError:
            logger.warning("OLLAMA_INJECT_USER_MESSAGE_AT=%r bad turn number; ignoring", raw)
            return cls()
        if n < 1 or not content:
            return cls()
        return cls(turn=n, content=content)

    def should_fire_after_turn(self, turn_index: int) -> bool:
        return self.turn == turn_index and bool(self.content)


@dataclass
class InjectToolCallAt:
    """Parsed `OLLAMA_INJECT_TOOL_CALL_AT` directive. Spec:
    `turn:N:tool_name:args_json` — at the start of turn N, **before**
    the model call, emit a `tool_invoked` event for `tool_name` with
    `args_json` (which MUST be valid JSON). The translator then either
    matches it against `Commission.resume.tool_cache` (cache hit → emit
    cached `tool_returned`) or executes the stub tool registry (cache
    miss). Demo / test instrumentation only; real agents drive tool
    calls from the model."""

    turn: int = 0
    tool_name: str = ""
    args: Any = None

    @classmethod
    def from_env(cls, raw: str | None = None) -> "InjectToolCallAt":
        if raw is None:
            raw = os.environ.get("OLLAMA_INJECT_TOOL_CALL_AT")
        if not raw:
            return cls()
        prefix = "turn:"
        if not raw.startswith(prefix):
            logger.warning("OLLAMA_INJECT_TOOL_CALL_AT=%r unrecognized; ignoring", raw)
            return cls()
        rest = raw[len(prefix):]
        parts = rest.split(":", 2)
        if len(parts) != 3:
            logger.warning("OLLAMA_INJECT_TOOL_CALL_AT=%r missing tool_name or args; ignoring", raw)
            return cls()
        n_str, tool_name, args_json = parts
        try:
            n = int(n_str)
        except ValueError:
            logger.warning("OLLAMA_INJECT_TOOL_CALL_AT=%r bad turn number; ignoring", raw)
            return cls()
        try:
            import json as _json
            args = _json.loads(args_json)
        except ValueError as e:
            logger.warning("OLLAMA_INJECT_TOOL_CALL_AT=%r bad JSON args: %s", raw, e)
            return cls()
        if n < 1 or not tool_name:
            return cls()
        return cls(turn=n, tool_name=tool_name, args=args)

    def should_fire_before_turn(self, turn_index: int) -> bool:
        return self.turn == turn_index and bool(self.tool_name)


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
        # Warm-rescue inputs from the Commission. None on fresh dispatches.
        self.resume_block = _extract_resume_block(config)
        # Test instrumentation (demo + smoke). Parsed once at construction.
        self.inject_user_message = InjectUserMessageAt.from_env()
        self.inject_tool_call = InjectToolCallAt.from_env()
        # Cap output length per turn. Without this, the model decides
        # when to stop, which on CPU-only Ollama with a long warm-rescue
        # prompt can run for minutes per turn and blow past the HTTP
        # timeout (we'd see runner-side `execution_backend_failure`s
        # that look like "rescue cascade" but are really "model is
        # too slow"). `0` / unset keeps the original model-decides
        # behavior for users on faster hardware.
        env_predict = os.environ.get("OLLAMA_NUM_PREDICT")
        self.num_predict = (
            int(env_predict) if env_predict and env_predict.strip() else 0
        )
        # httpx timeout. Default 300s — slow CPU inference (esp. with
        # long prompts) routinely exceeds the old 120s ceiling without
        # actually being broken. Override via OLLAMA_HTTP_TIMEOUT.
        timeout = float(os.environ.get("OLLAMA_HTTP_TIMEOUT") or 300.0)
        self.state = _RunState(run_id=run_id)
        self._http = httpx.Client(timeout=timeout)

    # ── public driver ────────────────────────────────────────────────────

    def run(self) -> str:
        """Drive the run to completion (or injected failure). Returns the
        terminal reason (`converged`, `error`) or `execution_backend_failure`
        when the rescue path was triggered."""
        try:
            # Decide starting seq + whether we're a rescued continuation.
            # Two signals:
            #   (a) Commission.resume.from_seq (canonical — supervisor told us)
            #   (b) next_seq query (fallback when no resume block — works
            #       for cold rescues that pre-date phase-2 supervisor work)
            # We prefer (a) when present; (b) handles legacy cold rescue.
            if self.resume_block is not None:
                start_seq = int(self.resume_block.get("from_seq", 0))
                is_rescued = True
                logger.info(
                    "warm-rescue continuation: from_seq=%d, "
                    "context.messages=%d, tool_cache=%d",
                    start_seq,
                    len(self._resume_messages()),
                    len(self._resume_tool_cache()),
                )
            else:
                try:
                    start_seq = self.client.next_seq(self.run_id)
                except httpx.HTTPError as e:
                    logger.warning("next_seq lookup failed (%s); starting at 0", e)
                    start_seq = 0
                is_rescued = start_seq > 0
                if is_rescued:
                    logger.info(
                        "cold-rescue continuation: starting at seq=%d (no resume block)",
                        start_seq,
                    )

            self.state.seq = start_seq
            if is_rescued:
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
            messages = self._seed_messages()
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
                # Test instrumentation: forced tool call BEFORE the model
                # turn. Lets the warm-rescue smoke prove tool-cache replay
                # without needing real model tool-calling.
                if self.inject_tool_call.should_fire_before_turn(turn_index):
                    self._fire_injected_tool_call()
                if self.rescue_fail_at.fire_before_turn(turn_index):
                    self._inject_failure(
                        f"RESCUE_FAIL_AT={self.rescue_fail_at.mode}: failing before turn {turn_index}"
                    )
                done, assistant = self._run_turn(turn_index, messages)
                last_turn = turn_index
                if assistant:
                    messages.append({"role": "assistant", "content": assistant})
                # Test instrumentation: inject a synthetic user message
                # between turns. The next turn's model call sees it as
                # part of the conversation. Used by the warm-rescue T2
                # smoke to introduce a recall token mid-conversation.
                if self.inject_user_message.should_fire_after_turn(turn_index):
                    messages.append(
                        {"role": "user", "content": self.inject_user_message.content}
                    )
                    # Also emit it as a text_emitted{role:user} so the
                    # supervisor's resume-block reconstruction picks it
                    # up — that's what makes the rescued runner see it.
                    self._emit_user_text(self.inject_user_message.content)
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
        """Append `event` to the trajectory at the next local seq, with
        retry-on-409 to handle supervisor-side concurrent inserts (e.g.,
        the supervisor's `avp.run_resumed` bracket landing at our
        next-free seq while we're mid-stream). On 409, re-query the
        authoritative `next_seq` from the supervisor, bump our local
        counter past it, and retry.

        Bounded retries: 3 total. Beyond that we log and give up — the
        trajectory has the event in a more authoritative form (the
        supervisor's own append), and any consumer scanning by type
        will still find the right event."""
        max_attempts = 3
        seq = self._next_seq()
        for attempt in range(1, max_attempts + 1):
            try:
                self.client.append_event(self.run_id, seq, event)
                return
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 409 or attempt == max_attempts:
                    logger.warning(
                        "event post failed (seq=%d, type=%s, attempt=%d/%d): %s",
                        seq, event.get("type"), attempt, max_attempts, e,
                    )
                    return
                # 409 → the supervisor (or someone) took this seq.
                # Re-discover the next-free seq and try again.
                try:
                    fresh = self.client.next_seq(self.run_id)
                except httpx.HTTPError as fetch_err:
                    logger.warning(
                        "next_seq re-fetch after 409 failed: %s", fetch_err
                    )
                    return
                logger.info(
                    "seq=%d collided (type=%s); retrying at seq=%d",
                    seq, event.get("type"), fresh,
                )
                seq = fresh
                # Keep our local counter ahead of the just-discovered
                # supervisor-side max so subsequent _next_seq calls
                # don't immediately collide again.
                self.state.seq = max(self.state.seq, seq + 1)
            except httpx.HTTPError as e:
                logger.warning("event post failed (seq=%d, type=%s): %s", seq, event.get("type"), e)
                return

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

        # Call Ollama. `options.num_predict` caps output tokens when
        # configured — bounds per-turn latency on slow (CPU-only) hosts.
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if self.num_predict > 0:
            body["options"] = {"num_predict": self.num_predict}
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

    def _seed_messages(self) -> list[dict[str, str]]:
        """Initial messages list for the model loop. When the
        Commission carries a `resume.context.messages`, seed from that
        verbatim — the supervisor has already reconstructed the
        prior runner's conversation. Otherwise fall back to
        `_initial_messages()` (Commission system_prompt + prompt)."""
        if self.resume_block is not None:
            resumed = self._resume_messages()
            if resumed:
                return [
                    {"role": m["role"], "content": m["content"]} for m in resumed
                ]
        return self._initial_messages()

    def _resume_messages(self) -> list[dict[str, str]]:
        """Extract `resume.context.messages` from the Commission as a
        plain list of dicts. Returns [] when absent / malformed."""
        if self.resume_block is None:
            return []
        ctx = self.resume_block.get("context") or {}
        msgs = ctx.get("messages") or []
        out: list[dict[str, str]] = []
        for m in msgs:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content")
            if isinstance(role, str) and isinstance(content, str):
                out.append({"role": role, "content": content})
        return out

    def _resume_tool_cache(self) -> list[dict[str, Any]]:
        """Extract `resume.tool_cache` from the Commission. Returns []
        when absent. Used by `_fire_injected_tool_call` to short-circuit
        cached invocations."""
        if self.resume_block is None:
            return []
        cache = self.resume_block.get("tool_cache") or []
        return [e for e in cache if isinstance(e, dict)]

    def _emit_user_text(self, text: str) -> None:
        """Emit a `text_emitted` event with `role: user`. Used by the
        inject-user-message test instrumentation so the supervisor's
        resume-block reconstruction picks the message up alongside
        assistant turns."""
        self._post(
            self._envelope(
                _T_TEXT_EMITTED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": _new_span_id(),
                    "parent_span_id": self.state.agent_span_id,
                    "role": "user",
                    "text": text,
                    "avp.runner": self._runner_attribution(),
                },
            )
        )

    # ── Tool dispatch (test instrumentation + cache replay) ─────────────

    def _fire_injected_tool_call(self) -> None:
        """Test-instrumentation tool dispatch. Emits `tool_invoked` for
        the configured tool + args. Then either:
          (a) cache hit (matching `resume.tool_cache` entry exists)
              → emit `tool_returned` (or `tool_failed`) with cached payload
          (b) cache miss
              → execute the stub tool registry (currently only `echo`,
                which returns its `args` verbatim). Real cache-miss
                tier behavior (replay_only → tool_failed, etc.) lands
                with real tool support; the stub just executes for the
                demo / smoke.
        Always increments a per-invocation span so the supervisor sees
        the standard tool_invoked/tool_returned pair shape."""
        tool_name = self.inject_tool_call.tool_name
        args = self.inject_tool_call.args
        invoke_span = _new_span_id()
        self._post(
            self._envelope(
                _T_TOOL_INVOKED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": invoke_span,
                    "parent_span_id": self.state.agent_span_id,
                    "avp.tool.name": tool_name,
                    "avp.tool.args": args,
                    "avp.runner": self._runner_attribution(),
                },
            )
        )
        cached = self._lookup_tool_cache(tool_name, args)
        if cached is not None:
            self._emit_tool_outcome_from_cache(invoke_span, cached)
            return
        # Cache miss → execute the stub tool registry.
        result = self._execute_stub_tool(tool_name, args)
        self._post(
            self._envelope(
                _T_TOOL_RETURNED,
                {
                    "trace_id": self.state.trace_id,
                    "span_id": _new_span_id(),
                    "parent_span_id": invoke_span,
                    "avp.tool.name": tool_name,
                    "avp.tool.result": result,
                    "avp.runner": self._runner_attribution(),
                },
            )
        )

    def _lookup_tool_cache(
        self, tool_name: str, args: Any
    ) -> dict[str, Any] | None:
        """Find the first `resume.tool_cache` entry matching the given
        tool_name + args. Args equality is by canonical JSON form (the
        supervisor pre-canonicalizes both halves; runners just do
        Python equality on the parsed JSON which is the same thing for
        normal payloads). Returns None on miss."""
        for entry in self._resume_tool_cache():
            if entry.get("tool_name") == tool_name and entry.get("args") == args:
                return entry
        return None

    def _emit_tool_outcome_from_cache(
        self, parent_span: str, entry: dict[str, Any]
    ) -> None:
        """Emit `tool_returned` (success) or `tool_failed` (failure)
        from a cache hit. The runner does NOT call the tool."""
        failure = entry.get("failure")
        if failure:
            self._post(
                self._envelope(
                    _T_TOOL_FAILED,
                    {
                        "trace_id": self.state.trace_id,
                        "span_id": _new_span_id(),
                        "parent_span_id": parent_span,
                        "avp.tool.name": entry.get("tool_name"),
                        "avp.error.message": failure.get("message", ""),
                        "avp.error.code": failure.get("code") or "replayed_failure",
                        "avp.runner": self._runner_attribution(),
                    },
                )
            )
        else:
            self._post(
                self._envelope(
                    _T_TOOL_RETURNED,
                    {
                        "trace_id": self.state.trace_id,
                        "span_id": _new_span_id(),
                        "parent_span_id": parent_span,
                        "avp.tool.name": entry.get("tool_name"),
                        "avp.tool.result": entry.get("result"),
                        "avp.runner": self._runner_attribution(),
                    },
                )
            )

    def _execute_stub_tool(self, tool_name: str, args: Any) -> Any:
        """Stub tool registry. v1 only has `echo` (returns args
        verbatim). Real tool dispatch lands when avp-ollama grows real
        tool support; for now this exists to let the warm-rescue smoke
        prove the tool_cache replay path end-to-end."""
        if tool_name == "echo":
            return args
        # Anything else — return a synthetic payload describing what
        # would have happened. Lets new test scenarios slot in without
        # adding registry entries.
        return {"_stub": True, "tool_name": tool_name, "args": args}


def _extract_resume_block(config: dict[str, Any]) -> dict[str, Any] | None:
    """Pull `Commission.resume` out of the Commission. Returns None when
    absent (fresh dispatch) or non-dict (defensive — shouldn't happen
    with the supervisor-built shape, but we don't trust adversarial
    input here)."""
    block = config.get("resume")
    if not isinstance(block, dict):
        return None
    return block
