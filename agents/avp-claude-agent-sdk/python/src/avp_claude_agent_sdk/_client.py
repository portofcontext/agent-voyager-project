"""`AVPClaudeSDKClient` -- the primary AVP surface for `claude-agent-sdk`.

Subclass of `ClaudeSDKClient` that emits a conforming AVP trajectory
across `connect()` / `receive_response()` / `disconnect()`. `query()`
is NOT overridden -- upstream it is fire-and-forget (returns `None`,
sends the prompt); the message iterator lives on `receive_response()`,
which is where AVP teeing happens.

Connect flow (two CLI subprocesses, per spec §2.1):

  1. **Probe subprocess** (in `connect()`): boot a transient `ClaudeSDKClient`, drain
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
     run session, with `Agent(<name>)` deny rules for the probed built-in
     subagents the Commission leaves out, and the user proceeds with
     `query()` / `receive_response()`.

The two-subprocess shape is the price of doing a spec-faithful
`agent_described` ("what is currently available", before Commission
filters) distinct from `agent_started` ("what the run will actually
use"). For Claude Code there is no static `describe` surface to probe;
booting a session and reading its init message is the only way to learn
the actual tool catalog (CLI built-ins, skill discovery, MCP states).

Cost: the CLI emits `init` only after a user message, which it then
sends to the model. The probe session points at a local stand-in endpoint
that records the tool definitions in that request and refuses it, so no
model spend happens; subprocess startup is the only overhead (see
`_probe_describe`).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import threading
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import ClaudeAgentOptions, McpStatusResponse

from avp.commission import Commission
from avp.preflight import preflight
from avp.sink import EventSink, stdio_sink
from avp.trajectory import ErrorCode, StopReason
from avp_claude_agent_sdk._commission import (
    UnsupportedProvider,
    apply_commission,
    apply_prompt,
)
from avp_claude_agent_sdk._emit import (
    emit_agent_stopped,
    emit_error,
    emit_prelude,
    handle_message,
)
from avp_claude_agent_sdk._runstate import current_run, new_run_state, reset_run, set_run
from avp_claude_agent_sdk._translator import (
    _AGENT_NAME,
    CATALOG_KEY,
    listed_descriptions,
    mcp_servers_from_status,
    skills_from_init,
    subagents_from_init,
    tools_from_init,
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
        self._probe: tuple[dict[str, Any] | None, McpStatusResponse] | None = None

    async def connect(self, prompt: str | AsyncIterable[dict[str, Any]] | None = None) -> None:
        # The probe runs first: withholding a built-in subagent takes its name,
        # and the real session's deny rules are fixed when it boots.
        self._probe = await _probe_describe(self._original_options)
        denied = _withheld_subagents(self._commission, self._probe[0])
        if denied:
            self.options = dataclasses.replace(
                self.options, disallowed_tools=[*self.options.disallowed_tools, *denied]
            )
        await super().connect(prompt)

    async def query(
        self, prompt: str | AsyncIterable[dict[str, Any]], session_id: str = "default"
    ) -> None:
        if not self._avp_prelude_emitted:
            # 1. The probe `connect()` ran: the agent's full pre-Commission
            #    surface, from a transient CLI session.
            if self._probe is None:
                self._probe = await _probe_describe(self._original_options)
            probe_init, probe_status = self._probe

            final_prompt = apply_prompt(self._commission, prompt)
            # 2. Set up RunState + emit the prelude. agent_described carries
            #    the probe view; agent_started carries the merged-state view
            state = new_run_state(
                self._sink,
                final_prompt,
                run_id=str(uuid.uuid4()),
                enabled_builtin_tools=(
                    (self._commission.enabled_builtin_tools or {}).get(_AGENT_NAME)
                    if self._commission
                    else None
                ),
                enabled_builtin_subagents=(
                    (self._commission.enabled_builtin_subagents or {}).get(_AGENT_NAME)
                    if self._commission
                    else None
                ),
                skills_filter=self.options.skills
                if isinstance(self.options.skills, list)
                else None,
            )
            state.catalog = (probe_init or {}).get(CATALOG_KEY) or {}
            self._avp_token = set_run(state)
            original_prompt = prompt if isinstance(prompt, str) else None

            await emit_prelude(
                state,
                self._original_options,
                commission=self._commission,
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

            # Fail fast (spec §4): a version pin for a different build, an
            # allow-list map without this agent's key, or an allow-listed tool
            # this agent doesn't offer (checked against the probe surface,
            # i.e. the pre-Commission view). Stop before any model turn.
            if self._commission is not None:
                failure = preflight(
                    self._commission,
                    agent_name=_AGENT_NAME,
                    agent_version=_agent_version(),
                    **_probed_names(probe_init, probe_status),
                )
                if failure is not None:
                    await emit_error(state, ValueError(failure[1]), error_code=failure[0])
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


def _probed_names(
    init_data: dict[str, Any] | None, status: McpStatusResponse
) -> dict[str, list[str] | None]:
    """The probed surface, by name, for `preflight`. An unknown surface (the
    probe failed) is `None`, which skips that check."""
    if init_data is None:
        return {"tools": None, "subagents": None, "skills": None, "mcp_servers": None}
    return {
        "tools": [t.name for t in tools_from_init(init_data, status) or []],
        "subagents": [s.name for s in subagents_from_init(init_data) or []],
        "skills": [s.name for s in skills_from_init(init_data) or []],
        "mcp_servers": [s.id for s in mcp_servers_from_status(status) or []],
    }


def _withheld_subagents(
    commission: Commission | None, init_data: dict[str, Any] | None
) -> list[str]:
    """`disallowed_tools` rules for the built-in subagents the Commission's
    allow-list leaves out: `Agent` itself when it allows none, else one
    `Agent(<name>)` per probed subagent it omits."""
    allow = ((commission.enabled_builtin_subagents or {}) if commission else {}).get(_AGENT_NAME)
    if allow is None:
        return []
    if not allow:
        return ["Agent"]
    probed = [s.name for s in subagents_from_init(init_data) or []] if init_data else []
    return [f"Agent({name})" for name in probed if name not in allow]


def _agent_version() -> str:
    """This build's `descriptor.agent_version` (the package version), the value
    `Commission.agent_versions` pins match against."""
    from importlib.metadata import version

    return version(_AGENT_NAME)


# The CLI's switches to Bedrock, Vertex, and Foundry, which would bypass the
# Anthropic base URL.
_NO_MODEL_ROUTE = {
    "CLAUDE_CODE_USE_BEDROCK": "0",
    "CLAUDE_CODE_USE_VERTEX": "0",
    "CLAUDE_CODE_USE_FOUNDRY": "0",
}


class _CatalogCapture:
    """A local stand-in for the Anthropic API that records the tools the CLI
    sends with its first model request, then refuses the request (400), so
    the probe learns each built-in's description and input schema without
    reaching a model. Those definitions exist only in the request; the CLI's
    `init` message names its tools and nothing more."""

    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}
        self.request: dict[str, Any] = {}
        self.seen = threading.Event()
        capture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_POST(self) -> None:
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
                except (ValueError, TypeError):
                    body = {}
                tools = body.get("tools") if isinstance(body, dict) else None
                # Side calls (titles, quota checks) carry `tools: []`; wait for
                # the agent's turn, which carries the full set.
                if isinstance(tools, list) and tools and not capture.seen.is_set():
                    for tool in tools:
                        if isinstance(tool, dict) and tool.get("name"):
                            capture.tools[tool["name"]] = {
                                k: tool[k] for k in ("description", "input_schema") if tool.get(k)
                            }
                    capture.request = body
                    capture.seen.set()
                data = json.dumps(
                    {
                        "type": "error",
                        "error": {"type": "invalid_request_error", "message": "avp probe"},
                    }
                ).encode()
                self.send_response(400)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def text(self) -> str:
        """Every string in the captured request (system, messages, tool
        descriptions), where the CLI lists subagents and skills."""
        parts: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, dict):
                for v in value.values():
                    walk(v)
            elif isinstance(value, list):
                for v in value:
                    walk(v)

        walk({k: v for k, v in self.request.items() if k != "tools"})
        walk([t.get("description") for t in self.request.get("tools") or [] if isinstance(t, dict)])
        return "\n".join(parts)

    @property
    def env(self) -> dict[str, str]:
        # A placeholder key: the CLI sends nothing without credentials, and the
        # host's real key has no business reaching the stand-in.
        return {
            "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{self.server.server_address[1]}",
            "ANTHROPIC_API_KEY": "avp-probe",
        }

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


# How long the probe waits, after `init`, for the CLI's first model request.
_CATALOG_WAIT_S = 10.0


async def _probe_describe(
    options: ClaudeAgentOptions | None,
) -> tuple[dict[str, Any] | None, McpStatusResponse]:
    """Boot a transient CLI session to discover the agent's pre-Commission
    capability surface; return `(init_data, mcp_status)`.

    The CLI reports its surface (`init`) only once it has a user message,
    and then calls the model. The probe session has no route to one: it
    points at a local `_CatalogCapture` with the cloud backends switched
    off, which records the tool definitions in that request and refuses it,
    so nothing is spent. The definitions ride on `init_data` under
    `CATALOG_KEY`. On any exception during probe, returns
    `(None, empty status)` so the caller can still emit a spec-conformant
    prelude (descriptor will carry identity + default_model only).
    """
    base = options if options is not None else ClaudeAgentOptions()
    capture = _CatalogCapture()
    probe = ClaudeSDKClient(
        options=dataclasses.replace(base, env={**base.env, **_NO_MODEL_ROUTE, **capture.env})
    )
    try:
        await probe.connect("probing claude capabilities")
        status = await probe.get_mcp_status()
        init_data: dict[str, Any] | None = None

        async for msg in probe.receive_response():
            if type(msg).__name__ == "SystemMessage" and getattr(msg, "subtype", None) == "init":
                init_data = getattr(msg, "data", None)
                break

        if init_data is not None:
            await asyncio.to_thread(capture.seen.wait, _CATALOG_WAIT_S)
            if capture.tools:
                text = capture.text
                catalog = {
                    "tools": capture.tools,
                    "subagents": listed_descriptions(text, init_data.get("agents") or []),
                    "skills": listed_descriptions(text, init_data.get("skills") or []),
                }
                init_data = {**init_data, CATALOG_KEY: catalog}
        return init_data, status
    except Exception:
        return None, McpStatusResponse(mcpServers=[])
    finally:
        capture.close()
        # Interrupt the doomed model call first: the CLI otherwise retries it
        # through the SDK's shutdown grace period.
        with contextlib.suppress(Exception):
            await probe.interrupt()
        with contextlib.suppress(Exception):
            await probe.disconnect()
