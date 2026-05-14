"""Idempotent monkeypatches for claude_agent_sdk.

`apply_patches()` / `restore_patches()` do direct attribute swaps on the
`claude_agent_sdk` module. A `_AVP_WRAPPED` marker on each replacement
makes double-setup a no-op.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import claude_agent_sdk

_AVP_WRAPPED = "_avp_wrapped"
_originals: dict[str, Any] = {}


def apply_patches() -> None:
    """Replace claude_agent_sdk symbols with AVP-emitting wrappers (idempotent)."""
    if getattr(claude_agent_sdk.query, _AVP_WRAPPED, False):
        return
    _originals["query"] = claude_agent_sdk.query
    wrapped = _wrap_query(claude_agent_sdk.query)
    setattr(wrapped, _AVP_WRAPPED, True)
    claude_agent_sdk.query = wrapped


def restore_patches() -> None:
    """Restore all patched symbols to their originals."""
    if "query" in _originals:
        claude_agent_sdk.query = _originals.pop("query")


def _wrap_query(original: Any) -> Any:
    """Passthrough wrapper; Stage 1 injects AVP emission into this wrapper."""

    async def wrapped(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        async for message in original(*args, **kwargs):
            yield message

    return wrapped
