"""Module-level monkeypatch for `claude_agent_sdk.ClaudeSDKClient`.

`setup_avp(sink)` swaps `claude_agent_sdk.ClaudeSDKClient` with a thin
subclass of `AVPClaudeSDKClient` that injects the configured sink at
construction time. Use this when you can't change your import to point
at `AVPClaudeSDKClient` directly; new code should prefer the explicit
wrapper.

Idempotent via a `_AVP_WRAPPED` marker on the patched class: calling
`setup_avp` again with a different sink mutates `_avp_sink` on the
existing wrapper rather than re-patching. The patch also walks
`sys.modules` and rebinds any `ClaudeSDKClient` attribute that still
points at the original class, mirroring the `ClassReplacementPatcher`
pattern -- callers that did `from claude_agent_sdk import
ClaudeSDKClient` before `setup_avp()` ran still pick up the wrapper.
"""

from __future__ import annotations

import sys
from typing import Any

import claude_agent_sdk
from claude_agent_sdk.types import ClaudeAgentOptions

from avp.agent.sink import EventSink, stdio_sink
from avp_claude_agent_sdk._client import AVPClaudeSDKClient

_AVP_WRAPPED = "_avp_wrapped"
_originals: dict[str, Any] = {}


def setup_avp(sink: EventSink = stdio_sink) -> None:
    """Patch `claude_agent_sdk.ClaudeSDKClient` to emit AVP trajectory.

    Idempotent. Pass a custom `sink` to redirect the trajectory (buffer,
    DB, NDJSON file, etc.). Calling again with a new sink updates the
    sink for future client instances without re-patching the class.
    """
    _ensure_patched(sink)


def _ensure_patched(sink: EventSink) -> None:
    """Apply the class swap, or update `_avp_sink` if already patched.

    The patched class reads `type(self)._avp_sink` at instance
    construction so subsequent `setup_avp(...)` calls take effect for
    new clients by mutating that class attribute, without re-running
    the patch.
    """
    if getattr(claude_agent_sdk.ClaudeSDKClient, _AVP_WRAPPED, False):
        claude_agent_sdk.ClaudeSDKClient._avp_sink = sink  # type: ignore[attr-defined]
        return

    original = claude_agent_sdk.ClaudeSDKClient

    class _PatchedClaudeSDKClient(AVPClaudeSDKClient):
        _avp_sink: EventSink = sink

        def __init__(
            self,
            options: ClaudeAgentOptions | None = None,
            transport: Any | None = None,
            *,
            sink: EventSink | None = None,
        ) -> None:
            super().__init__(
                options=options,
                transport=transport,
                sink=sink if sink is not None else type(self)._avp_sink,
            )

    setattr(_PatchedClaudeSDKClient, _AVP_WRAPPED, True)
    _originals["ClaudeSDKClient"] = original
    claude_agent_sdk.ClaudeSDKClient = _PatchedClaudeSDKClient  # type: ignore[misc]
    _sweep_modules(original, _PatchedClaudeSDKClient)


def _restore_patches() -> None:
    """Restore `ClaudeSDKClient` to the original. Testing helper only."""
    if "ClaudeSDKClient" not in _originals:
        return
    patched = claude_agent_sdk.ClaudeSDKClient
    original = _originals.pop("ClaudeSDKClient")
    claude_agent_sdk.ClaudeSDKClient = original
    _sweep_modules(patched, original)


def _sweep_modules(needle: Any, replacement: Any) -> None:
    """Walk `sys.modules` and rebind any `ClaudeSDKClient` attribute
    that currently holds `needle` to `replacement`.

    Skips our own package: modules under `avp_claude_agent_sdk` hold
    deliberate references to the upstream class (the probe in
    `_client._probe_describe` boots a transient unpatched client). If
    we rebound them, the wrapper's connect path would recursively
    instantiate itself instead of the original.
    """
    for module in list(sys.modules.values()):
        if module is None:
            continue
        name = getattr(module, "__name__", "")
        if name == "avp_claude_agent_sdk" or name.startswith("avp_claude_agent_sdk."):
            continue
        if getattr(module, "ClaudeSDKClient", None) is needle:
            module.ClaudeSDKClient = replacement  # type: ignore[attr-defined]
