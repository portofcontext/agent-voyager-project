"""`AVPClaudeSDKClient` -- the primary AVP surface for `claude-agent-sdk`.

Subclass of `ClaudeSDKClient` that emits a conforming AVP trajectory
across `connect()` / `receive_response()` / `disconnect()`. `query()`
is NOT overridden -- upstream it is fire-and-forget (returns `None`,
sends the prompt); the message iterator lives on `receive_response()`,
which is where AVP teeing happens.

Connect flow (two CLI subprocesses, per spec §2.1):

  1. **Probe subprocess**: boot a transient `ClaudeSDKClient`, drain
     the first `SystemMessage(subtype="init")`, capture
     `get_mcp_status()`, then disconnect. This populates
     `agent_described` with the full pre-Commission capability surface
     (CLI built-in tools, MCP servers + connection status, subagents,
     skills, resolved model).
  2. **Emit prelude**: `run_requested` → `agent_described` (probe data)
     → `agent_started` (merged-state view; today same surface as the
     descriptor since no Commission filtering is in scope -- Stage 3
     will add the merge).
  3. **Real subprocess**: `super().connect(prompt)` boots the actual
     run session and the user proceeds with `query()` /
     `receive_response()`.

The two-subprocess shape is the price of doing a spec-faithful
`agent_described` ("what is currently available", before Commission
filters) distinct from `agent_started` ("what the run will actually
use"). For Claude Code there is no static `describe` surface to probe;
booting a session and reading its init message is the only way to learn
the actual tool catalog (CLI built-ins, skill discovery, MCP states).

Cost: the probe session runs no model turn, so the heavy first-turn
context load ($0.05-$0.10) shouldn't fire on it. Subprocess startup +
init message exchange is the only overhead. TODO: empirically measure
probe cost; consider caching probe results across runs by options hash.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import ClaudeAgentOptions, McpStatusResponse

from avp.commission import Commission
from avp.envelope import new_trace_id
from avp.pricing import load_default_prices
from avp.sink import EventSink, stdio_sink
from avp.trajectory import ErrorCode, StopReason
from avp_claude_agent_sdk._commission import (
    UnsupportedProvider,
    apply_commission,
    apply_prompt,
)
from avp_claude_agent_sdk._emit import (
    emit_agent_described,
    emit_agent_stopped,
    emit_error,
    emit_run_requested,
    handle_message,
)
from avp_claude_agent_sdk._runstate import RunState, current_run, reset_run, set_run
from avp_claude_agent_sdk._translator import _AGENT_NAME, tools_from_init

# The four per-agent allowlist maps (Commission §4). Validated together in
# query(): each present map MUST carry this agent's key.
_ALLOWLIST_FIELDS = (
    "enabled_builtin_tools",
    "enabled_builtin_subagents",
    "enabled_builtin_skills",
    "enabled_builtin_mcp_servers",
)


class AVPClaudeSDKClient(ClaudeSDKClient):
    """AVP-instrumented `ClaudeSDKClient`. See module docstring for the
    probe-then-run connect flow."""

    def __init__(
        self,
        options: ClaudeAgentOptions | None = None,
        commission: Commission | None = None,
        transport: Any | None = None,
        *,
        sink: EventSink = stdio_sink,
    ) -> None:
        # An omitted options is the empty pre-Commission surface; normalize to
        # a real object so the probe + descriptor translation (which read
        # `options.system_prompt` etc.) don't dereference None.
        options = options if options is not None else ClaudeAgentOptions()
        # A non-anthropic provider is unsatisfiable for this SDK. Defer the
        # failure to query() so it lands in the trajectory (error_occurred +
        # agent_stopped) rather than crashing construction before any events.
        self._provider_error: UnsupportedProvider | None = None
        try:
            run_options = apply_commission(commission, options)
        except UnsupportedProvider as exc:
            self._provider_error = exc
            safe = commission.model_copy(update={"provider": None}) if commission else None
            run_options = apply_commission(safe, options)
        super().__init__(options=run_options, transport=transport)
        self._original_options = options
        self._commission = commission
        self._sink = sink
        self._avp_token = None
        self._avp_prelude_emitted = False
        # Set when a startup fail-fast (e.g. commission_collision) aborts the
        # run before the real session; `receive_response` then yields nothing.
        self._aborted = False

    async def query(
        self, prompt: str | AsyncIterable[dict[str, Any]], session_id: str = "default"
    ) -> None:
        if not self._avp_prelude_emitted:
            # 1. Probe pass: discover the agent's full pre-Commission surface
            #    via a transient CLI session.
            probe_init, probe_status = await _probe_describe(self._original_options)

            final_prompt = apply_prompt(self._commission, prompt)
            # 2. Set up RunState + emit the prelude. agent_described carries
            #    the probe view; agent_started carries the merged-state view
            state = RunState(
                prompt=final_prompt,
                trace_id=new_trace_id(),
                run_id=str(uuid.uuid4()),
                sink=self._sink,
                prices=load_default_prices(),
                enabled_builtin_tools=(
                    (self._commission.enabled_builtin_tools or {}).get(_AGENT_NAME)
                    if self._commission
                    else None
                ),
            )
            self._avp_token = set_run(state)
            original_prompt = prompt if isinstance(prompt, str) else None

            await emit_run_requested(state, commission=self._commission)
            await emit_agent_described(
                state,
                self._original_options,
                prompt=original_prompt,
                init_data=probe_init,
                status=probe_status,
            )

            self._avp_prelude_emitted = True

            # Fail fast (spec): the Commission asked for a provider this SDK
            # can't speak (Anthropic protocol only). Recorded in the trajectory.
            if self._provider_error is not None:
                await emit_error(
                    state,
                    self._provider_error,
                    error_code=ErrorCode.unsupported_provider,
                )
                await emit_agent_stopped(state, StopReason.error)
                self._aborted = True
                return None

            # Fail fast (spec §4.0): the Commission pins this agent at a
            # different build. Same-name surfaces can change behavior across
            # builds; refuse loudly instead of running an unvalidated one.
            pin = (
                (self._commission.agent_versions or {}).get(_AGENT_NAME)
                if self._commission
                else None
            )
            if pin is not None:
                actual = _agent_version()
                if pin != actual:
                    await emit_error(
                        state,
                        ValueError(
                            f"Commission pins {_AGENT_NAME} at {pin!r}; this build is {actual!r}"
                        ),
                        error_code=ErrorCode.unsupported_agent_version,
                    )
                    await emit_agent_stopped(state, StopReason.error)
                    self._aborted = True
                    return None

            # Fail fast (spec §4): each present allowlist map MUST carry this
            # agent's key (a map without it filters a surface the Commission
            # wasn't authored for on this agent), and every tool name under our
            # key must be one we offer. Validated against the probe surface
            # (pre-Commission tools); stop before any model turn.
            if self._commission is not None:
                missing_key = [
                    f
                    for f in _ALLOWLIST_FIELDS
                    if (m := getattr(self._commission, f)) is not None and _AGENT_NAME not in m
                ]
                if missing_key:
                    await emit_error(
                        state,
                        ValueError(f"no {_AGENT_NAME!r} entry in: " + ", ".join(missing_key)),
                        error_code=ErrorCode.commission_collision,
                    )
                    await emit_agent_stopped(state, StopReason.error)
                    self._aborted = True
                    return None
                allow = (self._commission.enabled_builtin_tools or {}).get(_AGENT_NAME)
                if allow is not None:
                    probe_tools = tools_from_init(probe_init, probe_status) if probe_init else None
                    known = {t.name for t in (probe_tools or [])}
                    unknown = [n for n in allow if n not in known]
                    if unknown:
                        await emit_error(
                            state,
                            ValueError(
                                "enabled_builtin_tools names not offered by the agent: "
                                + ", ".join(unknown)
                            ),
                            error_code=ErrorCode.commission_collision,
                        )
                        await emit_agent_stopped(state, StopReason.error)
                        self._aborted = True
                        return None

        return await super().query(final_prompt, session_id)

    async def receive_response(self) -> AsyncIterator[Any]:
        """Tee `super().receive_response()` through AVP emission.

        `CancelledError` → `agent_stopped("interrupted")`; other
        exceptions → `error_occurred` + `agent_stopped("error")`. Always
        sets `state.stopped` before re-raising so `disconnect()` doesn't
        double-fire.
        """
        # A startup fail-fast already emitted error_occurred + agent_stopped and
        # never started the real session; nothing to receive.
        if self._aborted:
            return
        state = current_run()
        try:
            async for message in super().receive_response():
                if state is not None:
                    await handle_message(self, state, message)
                yield message
        except BaseException as exc:
            if state is not None and not state.stopped:
                if isinstance(exc, Exception):
                    await emit_error(state, exc)
                    await emit_agent_stopped(state, StopReason.error)
                else:
                    # CancelledError (BaseException, not Exception).
                    await emit_agent_stopped(state, StopReason.interrupted)
            raise

    async def disconnect(self) -> None:
        state = current_run()
        if state is not None and not state.stopped:
            await emit_agent_stopped(state, StopReason.converged)
        if self._avp_token is not None:
            reset_run(self._avp_token)
            self._avp_token = None
        await super().disconnect()


def _agent_version() -> str:
    """This build's `descriptor.agent_version` (the package version), the value
    `Commission.agent_versions` pins match against."""
    from importlib.metadata import version

    return version(_AGENT_NAME)


async def _probe_describe(
    options: ClaudeAgentOptions | None,
) -> tuple[dict[str, Any] | None, McpStatusResponse]:
    """Boot a transient CLI session to discover the agent's pre-Commission
    capability surface; return `(init_data, mcp_status)`.

    The probe runs no `query()` so no model turn fires; only the
    subprocess startup + `init` message exchange happens. On any
    exception during probe, returns `(None, empty status)` so the caller
    can still emit a spec-conformant prelude (descriptor will carry
    identity + default_model only).
    """
    probe = ClaudeSDKClient(options=options)
    try:
        await probe.connect("probing claude capabilities")
        status = await probe.get_mcp_status()
        init_data: dict[str, Any] | None = None

        async for msg in probe.receive_response():
            if type(msg).__name__ == "SystemMessage" and getattr(msg, "subtype", None) == "init":
                init_data = getattr(msg, "data", None)
                break

        return init_data, status
    except Exception:
        return None, McpStatusResponse(mcpServers=[])
    finally:
        with contextlib.suppress(Exception):
            await probe.disconnect()
