"""TracedClaudeSDKClient — drop-in instrumentation for the Claude Agent SDK.

Wraps `claude_agent_sdk.ClaudeSDKClient` so an existing user loop:

    async with ClaudeSDKClient(options=options) as client:
        await client.connect(prompt)
        async for message in client.receive_response():
            handle(message)

becomes:

    async with TracedClaudeSDKClient(config=config, on_event=publish) as client:
        await client.connect(prompt)
        async for message in client.receive_response():
            handle(message)            # AEP events flow automatically

with AEP events on the wire — `agent_started`, `model_turn_*`,
`tool_invoked` / `tool_returned` / `subagent_invoked` / `subagent_returned`,
`verifier_evaluated`, `agent_stopped` — emitted as messages flow.

This is the Claude-Agent-SDK analogue of `aep_anthropic.AnthropicTracedClient`.
The SDK's ownership shape is different from the Messages API (the SDK runs
tools internally via PreToolUse/PostToolUse hooks rather than handing
tool_use blocks to the caller), so this wrapper inverts
`ClaudeAgentTranslator.run()` rather than wrapping a single SDK call: the
hook installation and message-translation logic runs UNDERNEATH the user's
async-for loop instead of inside the translator's own driver.

The configuration surface is the AEP `Config` — boundary, verifiers,
subagents, allowed_tools, model, system_prompt, prompt all flow through
the translator's `_build_sdk_options()` exactly as they do for the runner
CLI. v0.1 prototype: SDK-specific options (cwd, custom MCP servers
declared the SDK way, permission_mode) are not exposed here yet; if you
need those, use the runner CLI today and we'll thread them through Config
in a follow-up.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import BaseModel

from aep import AEPTracer, Config, StopReason, get_current_tracer
from aep_claude_agent.translator import ClaudeAgentTranslator, _VerifierHalt


class TracedClaudeSDKClient:
    """Async context manager wrapping `ClaudeSDKClient` with AEP wire events.

    Construct with the AEP `Config` and an `on_event` callback. On enter
    we emit `agent_started`, build the SDK options with AEP hooks installed
    (PreToolUse / PostToolUse / UserPromptSubmit / Stop / PreCompact /
    SubagentStart), open the underlying SDK client, and forward
    `connect()` / `query()` to it. `receive_response()` yields every
    SDK message after running it through the AEP translator — so consumer
    code that walks `AssistantMessage.content`, etc., keeps working
    unmodified, and AEP events for that message are guaranteed to have
    been emitted before the user's handler runs.

    On exit we run `at_end` verifiers, emit `agent_stopped`, and close
    the underlying SDK client. A halting verifier or unhandled exception
    overrides the stop reason; otherwise the run reports `converged`
    (or whatever `converged()` set).

    Tests inject fakes via `sdk_client_cls` / `sdk_options_cls` /
    `sdk_hook_matcher_cls` / `sdk_agent_definition_cls`, mirroring the
    translator's injection points.
    """

    def __init__(
        self,
        *,
        config: Config,
        on_event: Callable[[BaseModel], None],
        sdk_client_cls: Callable[..., Any] | None = None,
        sdk_options_cls: type | None = None,
        sdk_hook_matcher_cls: type | None = None,
        sdk_agent_definition_cls: type | None = None,
        parent_tracer: AEPTracer | None = None,
    ) -> None:
        """Standalone mode (default): pass `config` and `on_event`; the
        translator emits its own agent_started / agent_stopped lifecycle.

        Delegated mode: pass `parent_tracer` (typically supplied by the
        `traced_claude_sdk_client()` factory inside an outer `with
        AEPTracer(...)` block). The translator borrows the parent's
        trace_id / agent_span_id, emits via the parent's on_event sink,
        and suppresses its own lifecycle bookends so the wire stays one
        coherent tree."""
        self.config = config
        self._on_event = on_event
        self._parent_tracer = parent_tracer
        # The translator owns the wire — span tree, accounting, hook
        # callbacks, agent_started/stopped emission. We just orchestrate
        # its lifecycle around the user's async-for loop.
        self._translator = ClaudeAgentTranslator(
            config,
            on_event,
            sdk_client_cls=sdk_client_cls,
            sdk_options_cls=sdk_options_cls,
            sdk_hook_matcher_cls=sdk_hook_matcher_cls,
            sdk_agent_definition_cls=sdk_agent_definition_cls,
            parent_trace_id=parent_tracer.trace_id if parent_tracer else None,
            parent_agent_span_id=parent_tracer.agent_span_id if parent_tracer else None,
            suppress_lifecycle=parent_tracer is not None,
            parent_tracer=parent_tracer,
        )
        # The traced-client wrapper dispatches `after_each_turn` itself
        # AFTER yielding the message — see receive_response(). This way the
        # user's async-for body always sees a fully-translated message
        # before a halting verifier can terminate the iterator. Mirrors
        # AEPTracer where the verifier fires when the `with tracer.turn():`
        # block exits, not before.
        self._translator._run_inline_after_each_turn = False
        self._client: Any | None = None
        self._stop_reason: StopReason | None = None
        self._entered = False

    async def __aenter__(self) -> TracedClaudeSDKClient:
        if self._entered:
            raise RuntimeError(
                "TracedClaudeSDKClient cannot be reused; create a new instance per run"
            )
        self._entered = True
        self._translator._emit_agent_started()

        # Resolve the SDK client class lazily so tests can inject fakes; in
        # production this imports `claude_agent_sdk.ClaudeSDKClient`.
        if self._translator._sdk_client_cls is None:
            from claude_agent_sdk import (
                AgentDefinition,
                ClaudeAgentOptions,
                ClaudeSDKClient,
                HookMatcher,
            )

            self._translator._sdk_client_cls = ClaudeSDKClient
            self._translator._sdk_options_cls = ClaudeAgentOptions
            self._translator._sdk_hook_matcher_cls = HookMatcher
            self._translator._sdk_agent_definition_cls = AgentDefinition

        sdk_opts = self._translator._build_sdk_options()
        client_cls = self._translator._sdk_client_cls
        assert client_cls is not None
        self._client = client_cls(options=sdk_opts)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if self._client is not None:
                await self._client.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            self._finalize_lifecycle(exc_type)

    def _finalize_lifecycle(self, exc_type) -> None:
        """Run at_end verifiers and emit agent_stopped — UNLESS we're in
        delegated mode (an outer AEPTracer is in scope and will run them
        from its own __exit__)."""
        if self._parent_tracer is not None:
            return
        reason = self._stop_reason
        if reason is None and exc_type is not None:
            reason = StopReason.error
        try:
            self._translator._run_verifiers_for_trigger("at_end")
        except _VerifierHalt as halt:
            if reason is None or reason == StopReason.converged:
                reason = StopReason.converged if halt.success else StopReason.verifier_failed
        if reason is None:
            reason = StopReason.converged
        self._translator._emit_agent_stopped(reason)

    # ── Forwarded SDK surface ───────────────────────────────────────────────

    async def connect(self, prompt: str | None = None) -> None:
        if self._client is None:
            raise RuntimeError(
                "TracedClaudeSDKClient must be used as `async with` before calling connect()"
            )
        await self._client.connect(prompt)

    async def query(self, prompt: str, session_id: str = "default") -> None:
        if self._client is None:
            raise RuntimeError(
                "TracedClaudeSDKClient must be used as `async with` before calling query()"
            )
        await self._client.query(prompt, session_id)

    async def receive_response(self) -> AsyncIterator[Any]:
        """Yield messages from the SDK's stream after running each through
        the AEP translator.

        Order of operations per message:
          1. Translator processes the message — `model_turn_*`,
             `text_emitted`, and `cost_recorded` are emitted on the wire.
          2. The wrapper yields the message to the user's async-for body.
          3. After the user's body resumes us (via the next iteration or
             via `break`), the wrapper dispatches `after_each_turn`
             verifiers. If one halts, the iterator terminates cleanly and
             the run reports `reason=verifier_failed` on `__aexit__`.

        This mirrors `AEPTracer`'s `with tracer.turn():` semantic: the
        user's body executes BEFORE the trigger fires, so any work the
        user wants to do per-message (rendering, routing, logging) is
        guaranteed to run for every message that completed translation,
        even when a halting verifier eventually terminates the run.

        Halts arising from on_tool:* verifiers (the SDK runs tools
        internally, before the AssistantMessage that wraps them is
        yielded) propagate through the SDK's `await` and are caught at
        the outer try; same terminal behavior."""
        if self._client is None:
            raise RuntimeError(
                "TracedClaudeSDKClient must be used as `async with` before calling receive_response()"
            )
        halt_after_yield = False
        try:
            async for message in self._client.receive_response():
                if halt_after_yield:
                    break
                self._translator._on_sdk_message(message)
                yield message
                # After the user's body resumes us, run after_each_turn.
                # We can't `try/except` directly around the yield because
                # the user's body could legitimately raise; we only want
                # to swallow our own _VerifierHalt.
                try:
                    self._translator._run_verifiers_for_trigger("after_each_turn")
                except _VerifierHalt as halt:
                    self._stop_reason = (
                        StopReason.converged if halt.success else StopReason.verifier_failed
                    )
                    halt_after_yield = True
        except _VerifierHalt as halt:
            # Halts originating from inside the SDK's tool dispatch
            # (on_tool:* verifiers in PostToolUse) propagate here.
            self._stop_reason = StopReason.converged if halt.success else StopReason.verifier_failed
            return

    # ── User-driven control signals ─────────────────────────────────────────

    def converged(self) -> None:
        """Mark this run as converged. Honored on `__aexit__` when no
        other terminal condition (verifier halt, exception) has fired."""
        if self._stop_reason is None:
            self._stop_reason = StopReason.converged

    def pop_corrections(self) -> list[str]:
        """Drain the queue of `inject_correction` messages the translator
        has accumulated. The caller is responsible for handing them to the
        SDK as follow-up user prompts via `await client.query(correction)`
        between turns. Mirrors `AEPTracer.pop_corrections()` so the two
        drop-in surfaces have parallel APIs."""
        out = self._translator._pending_corrections
        self._translator._pending_corrections = []
        return out

    # ── Pass-through to the underlying SDK client ───────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access we don't explicitly wrap to the
        underlying SDK client. So e.g. SDK-specific helpers attached to
        `ClaudeSDKClient` keep working without us shadowing them."""
        # _client is set in __aenter__; callers that hit __getattr__ before
        # that should see a clear AttributeError.
        client = self.__dict__.get("_client")
        if client is None:
            raise AttributeError(
                f"TracedClaudeSDKClient has no attribute {name!r}; "
                "use `async with` to open the wrapper first"
            )
        return getattr(client, name)


def traced_claude_sdk_client(
    *,
    sdk_client_cls: Callable[..., Any] | None = None,
    sdk_options_cls: type | None = None,
    sdk_hook_matcher_cls: type | None = None,
    sdk_agent_definition_cls: type | None = None,
) -> TracedClaudeSDKClient:
    """Factory for the "wrap inside an active tracer" pattern. Requires an
    enclosing `with AEPTracer(config, on_event=...)` block; the factory
    pulls Config + on_event from that tracer and constructs a
    TracedClaudeSDKClient in delegated mode (its translator shares the
    tracer's trace_id and skips its own lifecycle bookends).

    Usage:

        with AEPTracer(config, on_event=publish):
            async with traced_claude_sdk_client() as client:
                await client.connect(prompt)
                async for message in client.receive_response():
                    ...

    Compare to the self-contained form:

        async with TracedClaudeSDKClient(config=cfg, on_event=publish) as client:
            ...

    Both produce the same wire shape. Use this factory when you have
    other AEP-instrumented work flowing through the same tracer (e.g.,
    a `wrap_anthropic` client for non-CASDK turns, or explicit
    `aep.tracer.tool(...)` blocks before the SDK opens).
    """
    tracer = get_current_tracer()
    if tracer is None:
        raise RuntimeError(
            "traced_claude_sdk_client() requires an active AEPTracer. Wrap your "
            "code in `with AEPTracer(config, on_event=...):` before calling, OR "
            "use TracedClaudeSDKClient(config=..., on_event=...) directly for "
            "the self-contained form."
        )
    return TracedClaudeSDKClient(
        config=tracer.config,
        on_event=tracer.on_event,
        sdk_client_cls=sdk_client_cls,
        sdk_options_cls=sdk_options_cls,
        sdk_hook_matcher_cls=sdk_hook_matcher_cls,
        sdk_agent_definition_cls=sdk_agent_definition_cls,
        parent_tracer=tracer,
    )


__all__ = ["TracedClaudeSDKClient", "traced_claude_sdk_client"]
