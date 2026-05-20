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

from avp.agent.sink import EventSink, stdio_sink
from avp.commission import Commission
from avp.envelope import new_trace_id
from avp.pricing import load_default_prices
from avp.trajectory import StopReason
from avp_claude_agent_sdk._commission import apply_commission, apply_prompt
from avp_claude_agent_sdk._emit import (
    emit_agent_described,
    emit_agent_stopped,
    emit_error,
    emit_run_requested,
    handle_message,
)
from avp_claude_agent_sdk._runstate import RunState, current_run, reset_run, set_run


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
        run_options = apply_commission(commission, options)
        super().__init__(options=run_options, transport=transport)
        self._original_options = options
        self._commission = commission
        self._sink = sink
        self._avp_token = None
        self._avp_prelude_emitted = False

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

        return await super().query(final_prompt, session_id)

    async def receive_response(self) -> AsyncIterator[Any]:
        """Tee `super().receive_response()` through AVP emission.

        `CancelledError` → `agent_stopped("interrupted")`; other
        exceptions → `error_occurred` + `agent_stopped("error")`. Always
        sets `state.stopped` before re-raising so `disconnect()` doesn't
        double-fire.
        """
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
