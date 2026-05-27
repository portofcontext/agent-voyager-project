"""Drop-in AVP instrumentation for the Anthropic SDK.

Two entry points; pick whichever fits how you wire the client.

**`AnthropicTracedClient(client, *, commission, on_event)`** — self-contained
context manager. Bundles the wrap with the run lifecycle in one object.
Best for a typical run where there's exactly one `Commission` + `on_event`.
This is what `examples/06_anthropic_traced_client.py` demonstrates.

**`wrap_anthropic(client)`** — pure-function wrap that returns a proxy
of the underlying Anthropic client. The proxy looks up the active
`_TracedRun` via a ContextVar on every call, so the same wrapped client
emits to whichever run is in scope. Use this when you have a long-lived
Anthropic client reused across many runs:

    client = wrap_anthropic(anthropic.Anthropic())  # one-time at startup

    with AnthropicTracedClient(real, commission=a, on_event=publish_a):
        client.messages.create(...)                 # emits to publish_a

Both forms emit byte-identical wire events for the same SDK response.
Both wrap `messages.create` (sync and async), `beta.messages.create`,
and forward all other attribute access to the underlying client.

This is observability over a loop the CALLER owns: it emits one
`run_requested` + `agent_started` on enter, one `assistant_message` per
`messages.create(...)`, optional `tool_invoked`/`tool_returned` and
`subagent_invoked`/`subagent_returned` via the `tool()` / `subagent()`
helpers, and `agent_stopped` on exit. It does NOT run a loop, dispatch
tools, or enforce caps. (`agent_described` is omitted: the raw Messages
API has no self-description to publish; full descriptor conformance is an
agent's job, see the reference agent in
`supervisors/simple-supervisor-example/examples/`.)
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

from avp.content import ToolResultBlock
from avp.envelope import ZERO_SPAN_ID, new_span_id, new_trace_id
from avp.trajectory import (
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    AssistantMessageData,
    AssistantMessageEvent,
    RunRequestedData,
    RunRequestedEvent,
    StopReason,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentReturnedData,
    SubagentReturnedEvent,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
)
from avp_anthropic.driver import DEFAULT_PRICES, PriceTable, _anthropic_response_to_avp
from avp_anthropic.translate import model_response_to_content, model_response_usage

if TYPE_CHECKING:
    from pydantic import BaseModel

    from avp.commission import Commission

_PROVIDER_NAME = "anthropic"

# Marker attribute set on wrapped clients so `wrap_anthropic` is idempotent —
# re-wrapping a wrapped client returns it unchanged. Namespaced so other
# instrumentation libraries that wrap the same SDK don't clobber each other.
_AVP_TRACED = "__avp_traced__"


# ── Active-run registry (contextvar) ──────────────────────────────────────────
#
# `with AnthropicTracedClient(...)` pushes its `_TracedRun` onto this ContextVar
# so `wrap_anthropic`-style proxies find it without an explicit argument (the
# OTel `current_span()` pattern). Module-local — NOT in the wire-types binding
# (which forbids opinionated tracers); this is the integrator's own shape.

_ACTIVE_RUN: ContextVar[_TracedRun | None] = ContextVar("avp_active_run", default=None)


def current_run() -> _TracedRun:
    """Return the active `_TracedRun` set by an enclosing
    `with AnthropicTracedClient(...)`. Raises if none is active so a missing
    context fails loudly rather than silently dropping events."""
    run = _ACTIVE_RUN.get()
    if run is None:
        raise RuntimeError(
            "No active traced run. Wrap your code in "
            "`with AnthropicTracedClient(client, commission=..., on_event=...):` "
            "before calling instrumented APIs."
        )
    return run


# ── Tool / subagent recorders (returned by the context managers) ─────────────


class _ToolRecorder:
    """Returned from `run.tool(...)`. Call `.record(output)` for success,
    `.fail(error)` for an execution error, or `.reject(output)` for a soft
    rejection. If none is called, the tool is treated as a generic failure."""

    def __init__(self) -> None:
        # (kind, payload, structured): "ok" | "error" | "rejected"
        self._outcome: tuple[str, str, Any | None] | None = None

    def record(self, output: str, *, structured: Any = None) -> None:
        self._outcome = ("ok", output, structured)

    def fail(self, error: str) -> None:
        self._outcome = ("error", error, None)

    def reject(self, output: str) -> None:
        self._outcome = ("rejected", output, None)

    def _block(self, tool_use_id: str) -> ToolResultBlock:
        kind, payload, structured = self._outcome or (
            "error",
            "tool block exited without recording an outcome",
            None,
        )
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=payload,
            structured_content=structured if isinstance(structured, dict) else None,
            is_error=kind == "error" or None,
        )


class _SubagentRecorder:
    """Returned from `run.subagent(...)`. Call `.record_result(text)` or
    `.fail(error)` before the block exits."""

    def __init__(self) -> None:
        self.result_text: str = ""
        self.reason: StopReason = StopReason.converged

    def record_result(self, text: str, *, reason: StopReason = StopReason.converged) -> None:
        self.result_text = text
        self.reason = reason

    def fail(self, error: str) -> None:
        self.result_text = error
        self.reason = StopReason.error


# ── The run (state + emission) ────────────────────────────────────────────────


class _TracedRun:
    """Holds per-run state and emits AVP events to `on_event`. One per
    `AnthropicTracedClient`. Sync (the wrapped `messages.create` is sync;
    the async proxies await the SDK call but emission stays sync)."""

    def __init__(
        self,
        commission: Commission,
        on_event: Callable[[BaseModel], None],
        *,
        prices: PriceTable,
        provider: str = _PROVIDER_NAME,
    ) -> None:
        self.commission = commission
        self.on_event = on_event
        self.prices = prices
        self.provider = provider
        self.trace_id = new_trace_id()
        self.agent_span_id = new_span_id()
        self.step = 0
        self.stopped = False
        self._stop_reason: StopReason | None = None

    @property
    def run_id(self) -> str:
        return self.commission.run_id

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        supervisor = self.commission.supervisor
        self.on_event(
            RunRequestedEvent(
                subject=self.run_id,
                data=RunRequestedData(
                    trace_id=self.trace_id,
                    span_id=new_span_id(),
                    parent_span_id=ZERO_SPAN_ID,
                    supervisor_name=supervisor.name if supervisor else None,
                    supervisor_version=supervisor.version if supervisor else None,
                    commission=self.commission,
                ),
            )
        )
        self.on_event(
            AgentStartedEvent(
                subject=self.run_id,
                data=AgentStartedData(
                    trace_id=self.trace_id,
                    span_id=self.agent_span_id,
                    parent_span_id=ZERO_SPAN_ID,
                    provider_name=self.provider,
                    operation_name="invoke_agent",
                    request_model=self.commission.model,
                    prompt=self.commission.prompt,
                    system_prompt=self.commission.system_prompt,
                    # Raw Messages API: no agent built-in tools to advertise
                    # (honest-null). MCP-surfaced tools, if any, are connected
                    # by the caller's own loop, not enumerated here.
                    tools=None,
                    thread_id=self.commission.thread_id,
                    tags=self.commission.tags,
                ),
            )
        )

    def converged(self) -> None:
        if self._stop_reason is None:
            self._stop_reason = StopReason.converged

    def stop(self, reason: StopReason) -> None:
        if self.stopped:
            return
        self.stopped = True
        self.on_event(
            AgentStoppedEvent(
                subject=self.run_id,
                data=AgentStoppedData(
                    trace_id=self.trace_id,
                    span_id=new_span_id(),
                    parent_span_id=self.agent_span_id,
                    reason=reason,
                ),
            )
        )

    # ── Turn ──────────────────────────────────────────────────────────────────

    def record_turn(self, response: Any, *, model: str, duration_ms: int) -> None:
        """Translate one `anthropic.Message` and emit `assistant_message`.

        Reuses the driver's single Anthropic→ModelResponse walker so the
        token / cost numbers are byte-identical to `AnthropicModelDriver`,
        then the shared ModelResponse→wire converters for content / usage.
        """
        mr = _anthropic_response_to_avp(response, model, self.prices, duration_ms)
        self.step += 1
        self.on_event(
            AssistantMessageEvent(
                subject=self.run_id,
                data=AssistantMessageData(
                    trace_id=self.trace_id,
                    span_id=new_span_id(),
                    parent_span_id=self.agent_span_id,
                    step=self.step,
                    duration_ms=mr.duration_ms,
                    content=model_response_to_content(mr),
                    usage=model_response_usage(mr),
                    cost_usd=mr.cost_usd,
                    cost_source=mr.cost_source,  # type: ignore[arg-type]
                    provider_name=self.provider,
                    request_model=model,
                    response_model=mr.response_model,
                    response_finish_reasons=mr.finish_reasons,
                ),
            )
        )

    # ── Tool ──────────────────────────────────────────────────────────────────

    @contextmanager
    def tool(self, *, call_id: str, name: str, input: dict[str, Any]) -> Iterator[_ToolRecorder]:
        """Bracket a tool dispatch: emit `tool_invoked` on enter, `tool_returned`
        on exit. The caller runs the tool inside the block and records the
        outcome on the yielded recorder."""
        span_id = new_span_id()
        t0 = time.monotonic()
        self.on_event(
            ToolInvokedEvent(
                subject=self.run_id,
                data=ToolInvokedData(
                    trace_id=self.trace_id,
                    span_id=span_id,
                    parent_span_id=self.agent_span_id,
                    step=self.step,
                    tool_call_id=call_id,
                    tool_name=name,
                    tool_input=dict(input),
                    tool_dispatch_target="local",
                ),
            )
        )
        rec = _ToolRecorder()
        try:
            yield rec
        finally:
            duration_ms = max(0, int((time.monotonic() - t0) * 1000))
            self.on_event(
                ToolReturnedEvent(
                    subject=self.run_id,
                    data=ToolReturnedData(
                        trace_id=self.trace_id,
                        span_id=new_span_id(),
                        parent_span_id=span_id,
                        step=self.step,
                        tool_call_id=call_id,
                        tool_name=name,
                        duration_ms=duration_ms,
                        tool_result=rec._block(call_id),
                    ),
                )
            )

    # ── Subagent ────────────────────────────────────────────────────────────

    @contextmanager
    def subagent(
        self, *, name: str, invocation_id: str | None = None, input: dict[str, Any] | None = None
    ) -> Iterator[_SubagentRecorder]:
        """Bracket a subagent delegation: emit `subagent_invoked` on enter,
        `subagent_returned` on exit (with `reason=error` if `.fail()` was
        called). The frame `span_id` is shared across the pair."""
        span_id = new_span_id()
        inv_id = invocation_id or f"sa-{new_span_id()}"
        t0 = time.monotonic()
        self.on_event(
            SubagentInvokedEvent(
                subject=self.run_id,
                data=SubagentInvokedData(
                    trace_id=self.trace_id,
                    span_id=span_id,
                    parent_span_id=self.agent_span_id,
                    step=self.step,
                    subagent_name=name,
                    subagent_invocation_id=inv_id,
                    subagent_input=dict(input or {}),
                ),
            )
        )
        rec = _SubagentRecorder()
        try:
            yield rec
        finally:
            duration_ms = max(0, int((time.monotonic() - t0) * 1000))
            self.on_event(
                SubagentReturnedEvent(
                    subject=self.run_id,
                    data=SubagentReturnedData(
                        trace_id=self.trace_id,
                        span_id=span_id,
                        parent_span_id=self.agent_span_id,
                        step=self.step,
                        subagent_name=name,
                        subagent_invocation_id=inv_id,
                        duration_ms=duration_ms,
                        subagent_result_text=rec.result_text,
                        subagent_reason=rec.reason,
                    ),
                )
            )


# ── Sync wrappers ──────────────────────────────────────────────────────────────


def _resolve_model(run: _TracedRun, kwargs: dict[str, Any]) -> str:
    return kwargs.get("model") or run.commission.model or "unspecified"


class _TracedMessages:
    """Wraps an `anthropic.Anthropic().messages` resource (or any sub-resource
    with the same `create()` shape — `beta.messages`, etc.).

    `_get_run` returns the `_TracedRun` events should be emitted to. The
    `wrap_anthropic` proxies pass `current_run` (lookup-on-each-call so the
    same wrapped client works across many runs); the `AnthropicTracedClient`
    self-contained form passes a `lambda: run` closure."""

    def __init__(self, real_messages: Any, *, get_run: Callable[[], _TracedRun]) -> None:
        self._real = real_messages
        self._get_run = get_run

    def __getattr__(self, name: str) -> Any:
        # Forward everything we don't explicitly wrap (count, retrieve, etc.).
        return getattr(self._real, name)

    @property
    def batches(self) -> Any:
        # Batch jobs aren't per-turn model calls; forward unwrapped.
        return self._real.batches

    def create(self, **kwargs: Any) -> Any:
        """Call the real SDK, emit one `assistant_message`, return the SDK's
        `anthropic.Message` unmodified so tool-dispatch logic that walks
        `resp.content` keeps working."""
        run = self._get_run()
        model = _resolve_model(run, kwargs)
        t0 = time.monotonic()
        response = self._real.create(**kwargs)
        duration_ms = int((time.monotonic() - t0) * 1000)
        run.record_turn(response, model=model, duration_ms=duration_ms)
        return response


class _TracedBeta:
    """Wraps `client.beta` so `client.beta.messages.create(...)` is
    instrumented the same way `client.messages.create(...)` is."""

    def __init__(self, real_beta: Any, *, get_run: Callable[[], _TracedRun]) -> None:
        self._real = real_beta
        self._messages = _TracedMessages(real_beta.messages, get_run=get_run)

    @property
    def messages(self) -> _TracedMessages:
        return self._messages

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _AnthropicProxy:
    """Top-level proxy for `anthropic.Anthropic()`. Wraps `messages` / `beta`;
    everything else falls through via `__getattr__`."""

    def __init__(self, client: Any, *, get_run: Callable[[], _TracedRun]) -> None:
        self.real = client
        self._get_run = get_run
        self._messages = _TracedMessages(client.messages, get_run=get_run)
        self._beta: _TracedBeta | None = None
        setattr(self, _AVP_TRACED, True)

    @property
    def messages(self) -> _TracedMessages:
        return self._messages

    @property
    def beta(self) -> _TracedBeta:
        if self._beta is None:
            self._beta = _TracedBeta(self.real.beta, get_run=self._get_run)
        return self._beta

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)


# ── Async wrappers ──────────────────────────────────────────────────────────────


class _AsyncTracedMessages:
    """Async sibling of `_TracedMessages` for `anthropic.AsyncAnthropic`."""

    def __init__(self, real_messages: Any, *, get_run: Callable[[], _TracedRun]) -> None:
        self._real = real_messages
        self._get_run = get_run

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    @property
    def batches(self) -> Any:
        return self._real.batches

    async def create(self, **kwargs: Any) -> Any:
        run = self._get_run()
        model = _resolve_model(run, kwargs)
        t0 = time.monotonic()
        response = await self._real.create(**kwargs)
        duration_ms = int((time.monotonic() - t0) * 1000)
        run.record_turn(response, model=model, duration_ms=duration_ms)
        return response


class _AsyncTracedBeta:
    def __init__(self, real_beta: Any, *, get_run: Callable[[], _TracedRun]) -> None:
        self._real = real_beta
        self._messages = _AsyncTracedMessages(real_beta.messages, get_run=get_run)

    @property
    def messages(self) -> _AsyncTracedMessages:
        return self._messages

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _AsyncAnthropicProxy:
    def __init__(self, client: Any, *, get_run: Callable[[], _TracedRun]) -> None:
        self.real = client
        self._get_run = get_run
        self._messages = _AsyncTracedMessages(client.messages, get_run=get_run)
        self._beta: _AsyncTracedBeta | None = None
        setattr(self, _AVP_TRACED, True)

    @property
    def messages(self) -> _AsyncTracedMessages:
        return self._messages

    @property
    def beta(self) -> _AsyncTracedBeta:
        if self._beta is None:
            self._beta = _AsyncTracedBeta(self.real.beta, get_run=self._get_run)
        return self._beta

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)


# ── Public surface ──────────────────────────────────────────────────────────────


def wrap_anthropic(client: Any) -> Any:
    """Wrap an Anthropic SDK client to emit AVP events for every model call.

    Returns a proxy that forwards every attribute to the underlying client;
    only the model-call surfaces (`messages.create`, `beta.messages.create`,
    sync and async) are instrumented. Idempotent — calling `wrap_anthropic`
    twice on the same client returns it unchanged.

    Requires an active `AnthropicTracedClient` context at call time. Inside
    one, the wrapped client emits to that run; outside one, instrumented
    methods raise `RuntimeError` rather than silently dropping events.
    """
    if getattr(client, _AVP_TRACED, False):
        return client
    type_name = type(client).__name__
    if "AsyncAnthropic" in type_name:
        return _AsyncAnthropicProxy(client, get_run=current_run)
    if "Anthropic" in type_name:
        return _AnthropicProxy(client, get_run=current_run)
    # Unknown shape — return as-is so a renamed/vendored SDK class doesn't
    # raise a confusing error.
    return client


class AnthropicTracedClient:
    """Self-contained context manager: bundles `wrap_anthropic` with the run
    lifecycle so a one-shot script doesn't need a separate scope block.

    Inside the `with`, the wrapper IS the wrapped Anthropic client —
    `client.messages.create(...)`, `client.beta.messages.create(...)` work
    exactly as the SDK does, and AVP events flow on the wire. Tool / subagent
    dispatch is exposed as `with client.tool(...)` / `with client.subagent(...)`.

    v0.1 leaves bounded execution to the caller — no caps are enforced.
    """

    def __init__(
        self,
        client: Any,
        *,
        commission: Commission,
        on_event: Callable[[BaseModel], None],
        prices: PriceTable | None = None,
        provider: str = _PROVIDER_NAME,
    ) -> None:
        self._client = client
        self._commission = commission
        self._on_event = on_event
        self._provider = provider
        self._prices = prices or DEFAULT_PRICES
        self._run: _TracedRun | None = None
        self._proxy: _AnthropicProxy | _AsyncAnthropicProxy | None = None
        self._token: Token[_TracedRun | None] | None = None
        self._entered = False

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> AnthropicTracedClient:
        if self._entered:
            raise RuntimeError(
                "AnthropicTracedClient cannot be reused; create a new instance per run"
            )
        self._entered = True
        self._run = _TracedRun(
            self._commission, self._on_event, prices=self._prices, provider=self._provider
        )
        # Push onto the ContextVar so wrap_anthropic proxies find this run.
        self._token = _ACTIVE_RUN.set(self._run)
        self._run.start()
        run = self._run
        get_run: Callable[[], _TracedRun] = lambda: run  # noqa: E731 — lambda is the right shape
        type_name = type(self._client).__name__
        if "AsyncAnthropic" in type_name:
            self._proxy = _AsyncAnthropicProxy(self._client, get_run=get_run)
        else:
            self._proxy = _AnthropicProxy(self._client, get_run=get_run)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        assert self._run is not None
        try:
            reason = StopReason.error if exc_type is not None else None
            if reason is None:
                reason = self._run._stop_reason or StopReason.converged
            self._run.stop(reason)
        finally:
            if self._token is not None:
                _ACTIVE_RUN.reset(self._token)
                self._token = None
        return False

    # ── Anthropic SDK surface (delegates to the proxy) ──────────────────────────

    @property
    def real(self) -> Any:
        return self._client

    @property
    def messages(self) -> Any:
        if self._proxy is None:
            raise RuntimeError(
                "AnthropicTracedClient must be used as `with` before calling messages.create()"
            )
        return self._proxy.messages

    @property
    def beta(self) -> Any:
        if self._proxy is None:
            raise RuntimeError("AnthropicTracedClient must be used as `with` before calling beta.*")
        return self._proxy.beta

    def __getattr__(self, name: str) -> Any:
        # Fall through to the underlying client for anything we haven't wrapped.
        # `_client` etc. are real attrs set in __init__; __getattr__ only fires
        # on failed lookup, so this never recurses.
        return getattr(self.__dict__["_client"], name)

    # ── AVP control surface (delegates to the run) ──────────────────────────────

    @contextmanager
    def tool(self, *, call_id: str, name: str, input: dict[str, Any]) -> Iterator[_ToolRecorder]:
        assert self._run is not None, "use as `with AnthropicTracedClient(...) as client:`"
        with self._run.tool(call_id=call_id, name=name, input=input) as t:
            yield t

    @contextmanager
    def subagent(
        self, *, name: str, invocation_id: str | None = None, input: dict[str, Any] | None = None
    ) -> Iterator[_SubagentRecorder]:
        assert self._run is not None, "use as `with AnthropicTracedClient(...) as client:`"
        with self._run.subagent(name=name, invocation_id=invocation_id, input=input) as sa:
            yield sa

    def converged(self) -> None:
        assert self._run is not None
        self._run.converged()

    @property
    def commission(self) -> Commission:
        return self._commission


__all__ = [
    "AnthropicTracedClient",
    "current_run",
    "format_event",
    "print_event",
    "wrap_anthropic",
]


def format_event(event: BaseModel) -> str | None:
    """One-line human-readable rendering of an AVP event, for examples and
    debugging. Pair with `print_event` as `on_event`. Returns None for events
    that are too noisy to print on their own."""
    cls = type(event).__name__
    data = getattr(event, "data", None)
    if data is None:
        return f"  {cls}"
    if cls == "AgentStartedEvent":
        bits = [f"agent_started run={event.subject!r}"]
        if data.request_model:
            bits.append(f"model={data.request_model}")
        if data.provider_name:
            bits.append(f"provider={data.provider_name}")
        return "  " + " ".join(bits)
    if cls == "AssistantMessageEvent":
        return (
            f"  [turn {data.step}] in={data.usage.input_tokens} "
            f"out={data.usage.output_tokens} cost=${data.cost_usd:.5f}"
        )
    if cls == "ToolInvokedEvent":
        return f"  -> {data.tool_name}({list(data.tool_input.keys())})"
    if cls == "ToolReturnedEvent":
        return f"  <- {data.tool_name}"
    if cls == "SubagentInvokedEvent":
        return f"  -> subagent {data.subagent_name!r} (invocation_id={data.subagent_invocation_id})"
    if cls == "SubagentReturnedEvent":
        head = data.subagent_result_text.replace("\n", " ")[:60]
        return f"  <- subagent {data.subagent_name!r} reason={data.subagent_reason} :: {head!r}"
    if cls == "AgentStoppedEvent":
        return f"  STOPPED reason={data.reason}"
    if cls == "ErrorOccurredEvent":
        return f"  ! {data.error_code}: {data.error_message}"
    return f"  {cls}"


def print_event(event: BaseModel) -> None:
    """Pretty-print an AVP event to stdout. Use as `on_event=print_event`."""
    line = format_event(event)
    if line is not None:
        print(line)
