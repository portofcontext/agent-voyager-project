"""Drop-in instrumentation for the Anthropic SDK.

Two entry points; pick whichever fits how you wire the client.

**`AnthropicTracedClient(client, *, config, on_event)`** — self-contained
context manager. Bundles the wrap with the tracer lifecycle in one
object. Best for a typical agent run where there's exactly one
`Config` + `on_event` per run. This is what `examples/06_anthropic_traced_client.py`
demonstrates.

**`wrap_anthropic(client)`** — pure-function wrap that returns a proxy
of the underlying Anthropic client. The proxy looks up the active
`AEPTracer` via a ContextVar on every call, so the same wrapped client
emits to whichever tracer is in scope. Use this when you have a
long-lived Anthropic client reused across many runs:

    client = wrap_anthropic(anthropic.Anthropic())  # one-time at startup

    with AEPTracer(config_a, on_event=publish_a):
        client.messages.create(...)                 # emits to publish_a

    with AEPTracer(config_b, on_event=publish_b):
        client.messages.create(...)                 # emits to publish_b

Both forms emit byte-identical wire events for the same SDK response.
Both wrap `messages.create` (sync and async), `beta.messages.create`,
and forward all other attribute access to the underlying client.

Boundary semantics: when the run hits its budget, the next
`messages.create()` raises `aep.BoundaryExhausted`. The
`AnthropicTracedClient` form swallows it on `__exit__`; with
`wrap_anthropic` the user catches it (or lets it propagate out of the
surrounding `with AEPTracer(...)` block).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from aep import (
    AEPTracer,
    BoundaryExhausted,
    SubagentScope,
    ToolCallRecorder,
    compute_cost,
    current_tracer,
)
from aep_anthropic.driver import DEFAULT_PRICES, PriceTable

if TYPE_CHECKING:
    from pydantic import BaseModel

    from aep import Config
    from aep.types import RunStateSnapshot


# Marker attribute set on wrapped clients so `wrap_anthropic` is idempotent —
# re-wrapping a wrapped client returns it unchanged. Namespaced so other
# instrumentation libraries that wrap the same SDK don't clobber each other.
_AEP_TRACED = "__aep_traced__"


# ── Shared instrumentation: the model-call seam ──────────────────────────────


def _record_anthropic_response(
    turn: Any, response: Any, *, model: str, prices: PriceTable, duration_ms: int
) -> None:
    """Extract usage / text from an `anthropic.Message` and call
    `turn.record(...)`. Single source of truth for the
    Anthropic→AEP-event conversion; both sync and async paths call
    this. Same conventions as `AnthropicModelDriver`: cache reads count
    as input tokens (per AEP §9.4)."""
    text_parts: list[str] = []
    for block in response.content or []:
        if getattr(block, "type", None) == "text":
            text_parts.append(getattr(block, "text", "") or "")
    text = "".join(text_parts) or None

    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0) if usage else 0
    cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0) if usage else 0

    # AEP §9.4: tokens_input INCLUDES cache reads. SDK reports fresh-only.
    aep_input = input_tokens + cache_read + cache_write
    cost, cost_source = compute_cost(
        model,
        input_tokens=aep_input,
        output_tokens=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        prices=prices,
    )
    stop_reason = getattr(response, "stop_reason", None)
    finish_reasons = [stop_reason] if isinstance(stop_reason, str) else None
    response_model = getattr(response, "model", None) or model

    turn.record(
        tokens_input=aep_input,
        tokens_output=output_tokens,
        cost_usd=cost,
        cost_source=cost_source,
        text=text,
        cache_read=cache_read or None,
        cache_write=cache_write or None,
        response_model=response_model,
        finish_reasons=finish_reasons,
        duration_ms=duration_ms,
    )


# ── Sync wrappers ────────────────────────────────────────────────────────────


class _TracedMessages:
    """Wraps an `anthropic.Anthropic().messages` resource (or any sub-resource
    with the same `create()` shape — `beta.messages`, etc.).

    `_get_tracer` returns the AEPTracer events should be emitted to. The
    `wrap_anthropic` proxies pass `current_tracer` (lookup-on-each-call so
    the same wrapped client works across many traces). The
    `AnthropicTracedClient` self-contained form passes a `lambda: tracer`
    (the tracer it owns) so no contextvar lookup is needed.
    """

    def __init__(
        self,
        real_messages: Any,
        *,
        get_tracer: Callable[[], AEPTracer],
        prices: PriceTable,
    ) -> None:
        self._real = real_messages
        self._get_tracer = get_tracer
        self._prices = prices

    def __getattr__(self, name: str) -> Any:
        # Forward everything we don't explicitly wrap (count, retrieve, etc.).
        return getattr(self._real, name)

    @property
    def batches(self) -> Any:
        # Batches are async / async-results — not part of the per-turn
        # model-call surface AEP cares about. Forward unwrapped so users who
        # call `.batches.create(...)` keep working; their batch jobs aren't
        # AEP turns.
        return self._real.batches

    def create(self, **kwargs: Any) -> Any:
        """Check boundary, open a turn, call the real SDK, record the
        response, close the turn. Returns the SDK's `anthropic.Message`
        unmodified so existing tool-dispatch logic that walks
        `resp.content` blocks keeps working."""
        tracer = self._get_tracer()
        if tracer.should_stop():
            raise BoundaryExhausted(reason=tracer._stop_reason)

        model = kwargs.get("model") or tracer.config.model or "unspecified"
        with tracer.turn() as turn:
            t0 = time.monotonic()
            response = self._real.create(**kwargs)
            duration_ms = int((time.monotonic() - t0) * 1000)
            _record_anthropic_response(
                turn, response, model=model, prices=self._prices, duration_ms=duration_ms
            )
        return response


class _TracedBeta:
    """Wraps `client.beta` so `client.beta.messages.create(...)` is
    instrumented the same way `client.messages.create(...)` is. Falls
    through to the real beta resource for everything else."""

    def __init__(
        self,
        real_beta: Any,
        *,
        get_tracer: Callable[[], AEPTracer],
        prices: PriceTable,
    ) -> None:
        self._real = real_beta
        self._messages = _TracedMessages(real_beta.messages, get_tracer=get_tracer, prices=prices)

    @property
    def messages(self) -> _TracedMessages:
        return self._messages

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _AnthropicProxy:
    """Top-level proxy for `anthropic.Anthropic()`. Wraps the surfaces that
    AEP cares about (`messages`, `beta`); everything else falls through to
    the underlying client via `__getattr__` (so `client.with_options(...)`,
    `client.api_key`, etc. keep working untouched)."""

    def __init__(
        self,
        client: Any,
        *,
        get_tracer: Callable[[], AEPTracer],
        prices: PriceTable,
    ) -> None:
        self.real = client
        self._get_tracer = get_tracer
        self._prices = prices
        self._messages = _TracedMessages(client.messages, get_tracer=get_tracer, prices=prices)
        self._beta: _TracedBeta | None = None
        # Mark the proxy itself so wrap_anthropic(proxy) is idempotent.
        setattr(self, _AEP_TRACED, True)

    @property
    def messages(self) -> _TracedMessages:
        return self._messages

    @property
    def beta(self) -> _TracedBeta:
        if self._beta is None:
            self._beta = _TracedBeta(
                self.real.beta, get_tracer=self._get_tracer, prices=self._prices
            )
        return self._beta

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)


# ── Async wrappers ───────────────────────────────────────────────────────────


class _AsyncTracedMessages:
    """Async sibling of `_TracedMessages` for `anthropic.AsyncAnthropic`."""

    def __init__(
        self,
        real_messages: Any,
        *,
        get_tracer: Callable[[], AEPTracer],
        prices: PriceTable,
    ) -> None:
        self._real = real_messages
        self._get_tracer = get_tracer
        self._prices = prices

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    @property
    def batches(self) -> Any:
        return self._real.batches

    async def create(self, **kwargs: Any) -> Any:
        tracer = self._get_tracer()
        if tracer.should_stop():
            raise BoundaryExhausted(reason=tracer._stop_reason)

        model = kwargs.get("model") or tracer.config.model or "unspecified"
        with tracer.turn() as turn:
            t0 = time.monotonic()
            response = await self._real.create(**kwargs)
            duration_ms = int((time.monotonic() - t0) * 1000)
            _record_anthropic_response(
                turn, response, model=model, prices=self._prices, duration_ms=duration_ms
            )
        return response


class _AsyncTracedBeta:
    def __init__(
        self,
        real_beta: Any,
        *,
        get_tracer: Callable[[], AEPTracer],
        prices: PriceTable,
    ) -> None:
        self._real = real_beta
        self._messages = _AsyncTracedMessages(
            real_beta.messages, get_tracer=get_tracer, prices=prices
        )

    @property
    def messages(self) -> _AsyncTracedMessages:
        return self._messages

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _AsyncAnthropicProxy:
    def __init__(
        self,
        client: Any,
        *,
        get_tracer: Callable[[], AEPTracer],
        prices: PriceTable,
    ) -> None:
        self.real = client
        self._get_tracer = get_tracer
        self._prices = prices
        self._messages = _AsyncTracedMessages(client.messages, get_tracer=get_tracer, prices=prices)
        self._beta: _AsyncTracedBeta | None = None
        setattr(self, _AEP_TRACED, True)

    @property
    def messages(self) -> _AsyncTracedMessages:
        return self._messages

    @property
    def beta(self) -> _AsyncTracedBeta:
        if self._beta is None:
            self._beta = _AsyncTracedBeta(
                self.real.beta, get_tracer=self._get_tracer, prices=self._prices
            )
        return self._beta

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)


# ── Public surface ───────────────────────────────────────────────────────────


def wrap_anthropic(client: Any, *, prices: PriceTable | None = None) -> Any:
    """Wrap an Anthropic SDK client to emit AEP events for every model call.

    Returns a proxy that forwards every attribute to the underlying client;
    only the model-call surfaces (`messages.create`, `beta.messages.create`,
    sync and async) are instrumented. The proxy is idempotent — calling
    `wrap_anthropic` twice on the same client returns it unchanged.

    Requires an active `AEPTracer` at call time. Inside a
    `with AEPTracer(config, on_event=...):` block, the wrapped client emits
    events to that tracer. Outside one, instrumented methods raise
    `RuntimeError` with a message pointing at the missing context — better
    than silently dropping events.

    Compare to `AnthropicTracedClient(client, config=..., on_event=...)`,
    which bundles the wrap with the tracer's lifecycle in one context
    manager. Both produce identical wire events; pick whichever feels
    natural. The wrap form is best for long-lived clients reused across
    many traces; the constructor form is best for one-shot scripts.
    """
    if getattr(client, _AEP_TRACED, False):
        return client
    type_name = type(client).__name__
    p = prices or DEFAULT_PRICES
    if "AsyncAnthropic" in type_name:
        return _AsyncAnthropicProxy(client, get_tracer=current_tracer, prices=p)
    if "Anthropic" in type_name:
        return _AnthropicProxy(client, get_tracer=current_tracer, prices=p)
    # Unknown shape — return as-is so users don't get a confusing error
    # if the SDK class is renamed or vendored.
    return client


class AnthropicTracedClient:
    """Self-contained context manager: bundles `wrap_anthropic` with the
    `AEPTracer` lifecycle so a one-shot script doesn't need a separate
    `with AEPTracer(...)` block.

    Inside the `with`, the wrapper IS the wrapped Anthropic client —
    `client.messages.create(...)`, `client.beta.messages.create(...)`,
    etc. work exactly as the SDK does, and AEP events flow on the wire.
    Tool / subagent dispatch is exposed directly on the wrapper as a
    convenience: `with client.tool(...)` and `with client.subagent(...)`.

    Boundary breach raises `BoundaryExhausted` from the next
    `messages.create()`; the wrapper's `__exit__` swallows that exception
    so the `with` block exits cleanly when the run hits its budget.
    """

    def __init__(
        self,
        client: Any,
        *,
        config: Config,
        on_event: Callable[[BaseModel], None],
        prices: PriceTable | None = None,
        provider: str = "anthropic",
    ) -> None:
        self._client = client
        self._config = config
        self._on_event = on_event
        self._provider = provider
        self._prices = prices or DEFAULT_PRICES
        self._tracer: AEPTracer | None = None
        self._proxy: _AnthropicProxy | _AsyncAnthropicProxy | None = None
        self._entered = False

    # ── Context manager ─────────────────────────────────────────────────────

    def __enter__(self) -> AnthropicTracedClient:
        if self._entered:
            raise RuntimeError(
                "AnthropicTracedClient cannot be reused; create a new instance per run"
            )
        self._entered = True
        self._tracer = AEPTracer(self._config, on_event=self._on_event, provider=self._provider)
        self._tracer.__enter__()
        # The tracer is now on the ContextVar. wrap_anthropic finds it via
        # current_tracer(); we'd get the same proxy by calling it here.
        # But constructing directly with a closure on `self._tracer`
        # avoids the contextvar lookup on every model call (small perf win
        # plus less indirection in the call stack when debugging).
        get_tracer = lambda: self._tracer  # noqa: E731 — lambda is the right shape here
        type_name = type(self._client).__name__
        if "AsyncAnthropic" in type_name:
            self._proxy = _AsyncAnthropicProxy(
                self._client, get_tracer=get_tracer, prices=self._prices
            )
        else:
            self._proxy = _AnthropicProxy(self._client, get_tracer=get_tracer, prices=self._prices)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        suppress = exc_type is BoundaryExhausted
        if suppress:
            self._tracer.__exit__(None, None, None)
        else:
            assert self._tracer is not None
            self._tracer.__exit__(exc_type, exc_val, exc_tb)
        return suppress

    # ── Anthropic SDK surface (delegates to the proxy) ──────────────────────

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
        # Fall through to the underlying client for anything we haven't
        # wrapped explicitly. Note: `_client`, `_proxy`, `_tracer`, etc.
        # are real attrs set in __init__; __getattr__ is only called when
        # normal lookup fails, so this never recurses.
        return getattr(self.__dict__["_client"], name)

    # ── AEP control surface (delegates to the internal tracer) ──────────────

    @contextmanager
    def tool(self, *, call_id: str, name: str, input: dict[str, Any]) -> Iterator[ToolCallRecorder]:
        assert self._tracer is not None, "use as `with AnthropicTracedClient(...) as client:`"
        with self._tracer.tool(call_id=call_id, name=name, input=input) as t:
            yield t

    @contextmanager
    def subagent(
        self, *, name: str, input: dict[str, Any] | None = None
    ) -> Iterator[SubagentScope]:
        assert self._tracer is not None, "use as `with AnthropicTracedClient(...) as client:`"
        with self._tracer.subagent(name=name, input=input) as sa:
            yield sa

    def converged(self) -> None:
        assert self._tracer is not None
        self._tracer.converged()

    def should_stop(self) -> bool:
        assert self._tracer is not None
        return self._tracer.should_stop()

    def pop_corrections(self) -> list[str]:
        assert self._tracer is not None
        return self._tracer.pop_corrections()

    @property
    def state(self) -> RunStateSnapshot:
        assert self._tracer is not None
        return self._tracer.state

    @property
    def config(self) -> Config:
        return self._config


__all__ = ["AnthropicTracedClient", "wrap_anthropic"]
