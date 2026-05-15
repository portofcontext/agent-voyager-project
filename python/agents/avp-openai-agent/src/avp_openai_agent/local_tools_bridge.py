"""Bridge user-defined local tools into OpenAI Agents SDK function tools.

The Agents SDK accepts callables decorated with `@function_tool` (or
`FunctionTool` instances) on `Agent.tools`. AVP's local-tool surface is
just a registry of `name → callable`. This module converts one to the
other so a supervisor's Commission-side tool registry doesn't have to
import `agents` directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def to_function_tools(
    tools: dict[str, Callable[..., Any]],
) -> list[Any]:
    """Wrap each `(name, callable)` into an `agents.function_tool`.

    Returns an empty list when the SDK isn't installed (tests can build
    Commissions without it). The decorator preserves the callable's
    signature; supervisors are responsible for ensuring callables expose
    JSON-schema-friendly types so the SDK can generate the OpenAI
    function spec.
    """
    if not tools:
        return []
    try:
        from agents import function_tool  # type: ignore[import-not-found]
    except ImportError:
        return []
    out: list[Any] = []
    for name, fn in tools.items():
        # `function_tool` reads the callable's name; if we want a custom
        # one, the decorator accepts `name_override`. Apply that when the
        # registry key differs from `fn.__name__`.
        if getattr(fn, "__name__", None) == name:
            out.append(function_tool(fn))
        else:
            out.append(function_tool(name_override=name)(fn))
    return out


__all__ = ["to_function_tools"]
