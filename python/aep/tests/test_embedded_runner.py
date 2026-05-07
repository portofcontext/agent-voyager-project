"""Embedded-runner smoke: prove `AEPRunner` works as a library embedded in a
long-lived worker, with all transports controlled by the embedder.

This is the seam a closed-source supervisor relies on: instead of spawning
runner subprocesses, the supervisor's worker imports `AEPRunner`, instantiates
it directly, and routes events + RPC replies through whatever durable
infrastructure the supervisor owns (Postgres, Kafka, Redis Streams, NATS).

What this test pins:
  - Streaming `on_event` callback fires synchronously, in order, BEFORE the
    event lands in `runner.trajectory` (so a worker writing to durable
    storage sees the same ordering an in-process consumer would).
  - The runner still populates `self.trajectory` for backwards-compat
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

from aep import Config, Tool
from aep.runner.drivers import (
    ModelResponse,
    ScriptedToolCall,
    SupervisorDriver,
    ToolDriver,
    ToolOutcome,
)
from aep.runner.mock import ScriptedModel, ScriptedTools
from aep.runner.runner import AEPRunner
from aep.types import (
    ToolExecResolvedEvent,
    ToolReturnedEvent,
)

# ── Streaming events: callback fires per emit ──────────────────────────────


def test_on_event_callback_streams_events_as_they_emit() -> None:
    """The embedded-worker pattern: a closed-source supervisor passes an
    `on_event` callback that writes each event to durable storage as it
    happens. This test substitutes a list for the durable store and pins
    that events arrive in the same order they would in `trajectory`."""
    streamed: list[BaseModel] = []
    runner = AEPRunner(
        config=Config(schema_version="0.1", run_id="streamed", model="test/mock"),
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
    runner.run()

    # Stream and trajectory MUST agree in order and content.
    assert len(streamed) == len(runner.trajectory)
    assert all(s is t for s, t in zip(streamed, runner.trajectory, strict=True))
    # And the run actually produced lifecycle events.
    types = [type(e).__name__ for e in streamed]
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"


def test_on_event_fires_before_trajectory_append() -> None:
    """A consumer reading `runner.trajectory` mid-run (e.g. a debugger
    hooked into the callback) MUST see consistent state: by the time the
    callback runs, the event is NOT yet in trajectory. This pins the
    ordering invariant."""
    seen_lengths: list[int] = []

    def callback(event: BaseModel) -> None:
        # Capture trajectory length AT the moment the callback fires.
        seen_lengths.append(len(runner.trajectory))

    runner = AEPRunner(
        config=Config(schema_version="0.1", run_id="ordering", model="test/mock"),
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
    runner.run()
    # First callback ran when trajectory was empty (event 0 not yet appended);
    # second callback ran with one prior event in trajectory; etc.
    assert seen_lengths == list(range(len(runner.trajectory)))


def test_no_on_event_keeps_trajectory_path_unchanged() -> None:
    """Backwards-compat: existing callers that pass NO on_event MUST see
    runner behaviour unchanged — events accumulate in `trajectory`, no
    callback is invoked."""
    runner = AEPRunner(
        config=Config(schema_version="0.1", run_id="no-cb", model="test/mock"),
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
    runner.run()
    assert runner.trajectory  # populated as before
    types = [type(e).__name__ for e in runner.trajectory]
    assert "AgentStartedEvent" in types
    assert "AgentStoppedEvent" in types


def test_on_event_exception_aborts_run_loudly() -> None:
    """If the callback raises (durable store unavailable, schema-validation
    failure, anything), the runner MUST propagate the exception rather than
    silently dropping events — better to fail the run than to ship a
    trajectory with holes the supervisor doesn't know about."""

    def bad_callback(event: BaseModel) -> None:
        # Fail on the first event we see.
        raise RuntimeError("durable store unavailable")

    runner = AEPRunner(
        config=Config(schema_version="0.1", run_id="cb-fail", model="test/mock"),
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
        runner.run()
    except RuntimeError as e:
        assert "durable store unavailable" in str(e)
        # Trajectory MUST NOT contain the failed event — the order is
        # callback first, append second; if callback raised, append
        # never happened.
        assert runner.trajectory == []
        return
    raise AssertionError("expected RuntimeError to propagate from the callback")


# ── End-to-end: embedded supervisor pattern (events out, RPC replies in) ──


def test_embedded_worker_pattern_with_custom_supervisor_driver() -> None:
    """The full embedded picture: a Rust supervisor enqueues a Config, a
    Python worker pulls it, instantiates AEPRunner with a custom
    SupervisorDriver that reads RPC replies from durable infra (here
    a `_DurableQueue` stand-in), and an `on_event` callback that writes
    events to a durable store (here `event_log`). The runner runs end-to-
    end with no subprocess, no HTTP, no transport AEP knows about — the
    supervisor owns the transport entirely.

    What's pinned: the runner emits a tool_exec_request, the custom
    supervisor driver returns a reply via the queue, the runner records
    tool_exec_resolved + tool_returned, and the run converges. Same
    wire-format trajectory you'd get over stdio, just delivered through
    callbacks the embedder controls.
    """
    # ── The "durable infrastructure" stand-in ──────────────────────
    event_log: list[BaseModel] = []

    class _ProgrammedSupervisor(SupervisorDriver):
        """Replies to any tool_exec_request with a hardcoded result.
        In a real deployment `get_tool_exec_response` would block on a
        Postgres LISTEN, a Kafka consumer, a Redis BRPOP, etc. — same
        shape, different durable medium."""

        def observe(self, event: BaseModel) -> None:
            # No-op: a real supervisor would record the event to durable
            # storage here. The embedded test does that via on_event below.
            pass

        def get_tool_exec_response(self, request_id: str, timeout_ms: int) -> Any:
            from aep.types import ToolExecResolvedData

            # Real impl would correlate request_id back to the original
            # span_id stored at request time; we use placeholders the runner
            # re-stamps with its own trace context.
            return ToolExecResolvedEvent(
                subject="embedded",
                source="aep://supervisor",
                data=ToolExecResolvedData.model_validate(
                    {
                        "trace_id": "0" * 32,
                        "span_id": "0" * 16,
                        "parent_span_id": "0" * 16,
                        "aep.request_id": request_id,
                        "rpc": {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": "user-found-42",
                        },
                    }
                ),
            )

        def get_approval_response(self, approval_id: str, timeout_ms: int) -> Any:
            return None  # not used in this test

    # ── The embedded runner ─────────────────────────────────────────
    cfg = Config(
        schema_version="0.1",
        run_id="embedded",
        model="test/mock",
        tools=[
            Tool(
                name="lookup_user",
                description="RPC tool routed to durable supervisor.",
                inputSchema={"type": "object", "properties": {}, "additionalProperties": True},
            )
        ],
    )
    runner = AEPRunner(
        config=cfg,
        model=ScriptedModel(
            [
                ModelResponse(
                    tokens_input=10,
                    tokens_output=5,
                    cost_usd=0.0001,
                    duration_ms=1,
                    tool_calls=[
                        ScriptedToolCall(call_id="c1", tool="lookup_user", input={"id": 42})
                    ],
                    converged=False,
                ),
                ModelResponse(
                    tokens_input=5,
                    tokens_output=3,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="found user-found-42",
                    converged=True,
                ),
            ]
        ),
        tools=_NoLocalTools(),
        supervisor=_ProgrammedSupervisor(),
        on_event=event_log.append,
    )
    runner.run()

    # Streamed event log MUST contain the full agent lifecycle + the
    # RPC pair. Everything a real supervisor needs is in the log.
    types = {type(e).__name__ for e in event_log}
    assert "AgentStartedEvent" in types
    assert "ToolExecRequestEvent" in types  # runner emitted (from the supervisor RPC)
    assert "ToolExecResolvedEvent" in types  # custom driver provided
    assert "ToolInvokedEvent" in types
    assert "ToolReturnedEvent" in types
    assert "AgentStoppedEvent" in types

    # Stream and trajectory still agree.
    assert event_log == runner.trajectory

    # The result the supervisor returned made it through to the model
    # (recorded on tool_returned.data["aep.tool.result.text"]).
    returned = next(e for e in event_log if isinstance(e, ToolReturnedEvent))
    assert "user-found-42" in returned.data.aep_tool_result_text


# ── Helpers ─────────────────────────────────────────────────────────────────


class _NoopSupervisor(SupervisorDriver):
    """SupervisorDriver impl that never gets called — for tests with no
    Config.tools. The embedded pattern uses a real impl; this is just a
    stub."""

    def observe(self, event: BaseModel) -> None:
        pass

    def get_tool_exec_response(self, request_id: str, timeout_ms: int) -> Any:
        raise RuntimeError("noop supervisor: should not be called in this test")

    def get_approval_response(self, approval_id: str, timeout_ms: int) -> Any:
        return None


class _NoLocalTools(ToolDriver):
    """ToolDriver that claims nothing as local — so all tool calls route
    to the SupervisorDriver. Lets the embedded RPC pattern exercise."""

    def is_local(self, tool: str) -> bool:
        return False

    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome:
        return ToolOutcome(error=f"no local tool {tool!r}")
