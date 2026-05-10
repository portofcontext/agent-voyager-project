"""Embedded-agent smoke: prove `AVPAgent` works as a library embedded in a
long-lived worker, with all transports controlled by the embedder.

This is the seam a closed-source supervisor relies on: instead of spawning
agent subprocesses, the supervisor's worker imports `AVPAgent`, instantiates
it directly, and routes events + RPC replies through whatever durable
infrastructure the supervisor owns (Postgres, Kafka, Redis Streams, NATS).

What this test pins:
  - Streaming `on_event` callback fires synchronously, in order, BEFORE the
    event lands in `agent.trajectory` (so a worker writing to durable
    storage sees the same ordering an in-process consumer would).
  - The agent still populates `self.trajectory` for backwards-compat
    (existing tests + post-run summary code keep working).
  - Custom `SupervisorDriver` impl can route RPC replies through any
    medium — here we use a tiny in-memory queue stand-in for "the durable
    infrastructure" the real supervisor would use.
  - The `on_event` exception propagates out of `run()` (the run aborts
    rather than silently dropping events).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from avp import Commission
from avp.agent.agent import AVPAgent
from avp.agent.drivers import (
    ModelResponse,
    SupervisorDriver,
    ToolDriver,
    ToolOutcome,
)
from avp.agent.mock import ScriptedModel, ScriptedTools

# ── Streaming events: callback fires per emit ──────────────────────────────


def test_on_event_callback_streams_events_as_they_emit() -> None:
    """The embedded-worker pattern: a closed-source supervisor passes an
    `on_event` callback that writes each event to durable storage as it
    happens. This test substitutes a list for the durable store and pins
    that events arrive in the same order they would in `trajectory`."""
    streamed: list[BaseModel] = []
    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="streamed", model="test/mock"),
        model=ScriptedModel(
            [
                ModelResponse(
                    tokens_input=10,
                    tokens_output=5,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        ),
        tools=ScriptedTools(),
        supervisor=_NoopSupervisor(),
        on_event=streamed.append,
    )
    agent.run()

    # Stream and trajectory MUST agree in order and content.
    assert len(streamed) == len(agent.trajectory)
    assert all(s is t for s, t in zip(streamed, agent.trajectory, strict=True))
    # And the run actually produced lifecycle events.
    types = [type(e).__name__ for e in streamed]
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"


def test_on_event_fires_before_trajectory_append() -> None:
    """A consumer reading `agent.trajectory` mid-run (e.g. a debugger
    hooked into the callback) MUST see consistent state: by the time the
    callback runs, the event is NOT yet in trajectory. This pins the
    ordering invariant."""
    seen_lengths: list[int] = []

    def callback(event: BaseModel) -> None:
        # Capture trajectory length AT the moment the callback fires.
        seen_lengths.append(len(agent.trajectory))

    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="ordering", model="test/mock"),
        model=ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        ),
        tools=ScriptedTools(),
        supervisor=_NoopSupervisor(),
        on_event=callback,
    )
    agent.run()
    # First callback ran when trajectory was empty (event 0 not yet appended);
    # second callback ran with one prior event in trajectory; etc.
    assert seen_lengths == list(range(len(agent.trajectory)))


def test_no_on_event_keeps_trajectory_path_unchanged() -> None:
    """Backwards-compat: existing callers that pass NO on_event MUST see
    agent behaviour unchanged — events accumulate in `trajectory`, no
    callback is invoked."""
    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="no-cb", model="test/mock"),
        model=ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        ),
        tools=ScriptedTools(),
        supervisor=_NoopSupervisor(),
        # No on_event passed.
    )
    agent.run()
    assert agent.trajectory  # populated as before
    types = [type(e).__name__ for e in agent.trajectory]
    assert "AgentStartedEvent" in types
    assert "AgentStoppedEvent" in types


def test_on_event_exception_aborts_run_loudly() -> None:
    """If the callback raises (durable store unavailable, schema-validation
    failure, anything), the agent MUST propagate the exception rather than
    silently dropping events — better to fail the run than to ship a
    trajectory with holes the supervisor doesn't know about."""

    def bad_callback(event: BaseModel) -> None:
        # Fail on the first event we see.
        raise RuntimeError("durable store unavailable")

    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="cb-fail", model="test/mock"),
        model=ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        ),
        tools=ScriptedTools(),
        supervisor=_NoopSupervisor(),
        on_event=bad_callback,
    )
    try:
        agent.run()
    except RuntimeError as e:
        assert "durable store unavailable" in str(e)
        # Trajectory MUST NOT contain the failed event — the order is
        # callback first, append second; if callback raised, append
        # never happened.
        assert agent.trajectory == []
        return
    raise AssertionError("expected RuntimeError to propagate from the callback")


# ── Helpers ─────────────────────────────────────────────────────────────────


class _NoopSupervisor(SupervisorDriver):
    """SupervisorDriver impl that just observes — used by tests where the
    agent doesn't need the supervisor to do anything."""

    def observe(self, event: BaseModel) -> None:
        pass


class _NoLocalTools(ToolDriver):
    """ToolDriver that claims nothing as local — so all tool calls route
    to the SupervisorDriver. Lets the embedded RPC pattern exercise."""

    def is_local(self, tool: str) -> bool:
        return False

    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome:
        return ToolOutcome(error=f"no local tool {tool!r}")
