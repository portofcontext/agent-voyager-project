"""Idempotent monkeypatches for claude_agent_sdk.

`setup_avp(sink)` stores the sink and calls `_ensure_patched()`, which does
a direct attribute swap on the `claude_agent_sdk` module. A `_AVP_WRAPPED`
marker makes double-patching a no-op. `run_avp_agent` calls `_ensure_patched`
directly so it doesn't overwrite a user-configured sink.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import claude_agent_sdk
from claude_agent_sdk.types import AssistantMessage, ClaudeAgentOptions

from avp._envelope import new_trace_id
from avp.agent.sink import EventSink, stdio_sink
from avp_claude_agent_sdk._emit import emit_model_turn_started, emit_prelude
from avp_claude_agent_sdk._runstate import RunState, current_run, reset_run, set_run

_AVP_WRAPPED = "_avp_wrapped"
_originals: dict[str, Any] = {}
_configured_sink: EventSink = stdio_sink


def setup_avp(sink: EventSink = stdio_sink) -> None:
    """Instrument claude_agent_sdk with AVP trajectory emission (idempotent).

    Pass a custom `sink` to redirect the trajectory (e.g. to a buffer or DB).
    Calling again with a new sink updates the sink without re-patching.
    """
    global _configured_sink
    _configured_sink = sink
    _ensure_patched()


def _ensure_patched() -> None:
    """Apply patches without touching the configured sink. For internal use.

    Also updates any module that did `from claude_agent_sdk import query`
    before setup_avp() was called, mirroring Braintrust's ClassReplacementPatcher
    approach of scanning sys.modules for stale references.
    """
    if getattr(claude_agent_sdk.query, _AVP_WRAPPED, False):
        return
    original = claude_agent_sdk.query
    wrapped = _wrap_query(original)
    setattr(wrapped, _AVP_WRAPPED, True)
    _originals["query"] = original
    claude_agent_sdk.query = wrapped
    for module in sys.modules.values():
        if getattr(module, "query", None) is original:
            module.query = wrapped


def _restore_patches() -> None:
    """Restore all patched symbols to their originals. For testing only."""
    if "query" in _originals:
        claude_agent_sdk.query = _originals.pop("query")


def _wrap_query(original: Any) -> Any:
    """Tee'd async generator: emits AVP prelude + per-turn events, passes messages through."""

    async def wrapped(**kwargs: Any) -> AsyncGenerator[Any, None]:
        prompt_raw = kwargs.get("prompt")
        prompt_text = prompt_raw if isinstance(prompt_raw, str) else None
        options: ClaudeAgentOptions = kwargs.get("options") or ClaudeAgentOptions()

        state = current_run()
        token = None
        if state is None:
            state = RunState(
                trace_id=new_trace_id(),
                run_id=str(uuid.uuid4()),
                sink=_configured_sink,
            )
            token = set_run(state)

        try:
            await emit_prelude(state, prompt_text, options)
            step = 0
            async for message in original(**kwargs):
                if isinstance(message, AssistantMessage):
                    step += 1
                    await emit_model_turn_started(state, step)
                yield message
        finally:
            if token is not None:
                reset_run(token)

    return wrapped
