"""to_function_tools — Commission tool registry → openai-agents FunctionTool.

The bridge accepts `{name: callable}` and returns a list of `agents`-side
function tools so supervisors don't have to import `agents` themselves.
"""

from __future__ import annotations

import importlib.util

import pytest
from avp_openai_agent import to_function_tools

_HAS_SDK = importlib.util.find_spec("agents") is not None


def test_empty_registry_returns_empty_list() -> None:
    assert to_function_tools({}) == []


def test_returns_empty_when_sdk_missing(monkeypatch) -> None:
    """If openai-agents isn't installed, the bridge degrades gracefully so
    Commission-building code still works for `describe` / unit-test paths.
    Simulate by hiding the `agents` import."""
    import sys

    # Stash the real `agents` module if present, replace with a sentinel
    # that raises ImportError when the bridge tries to import from it.
    real = sys.modules.pop("agents", None)
    try:

        class _BrokenAgents:
            def __getattr__(self, name: str) -> object:
                raise ImportError(f"simulated missing: agents.{name}")

        sys.modules["agents"] = _BrokenAgents()  # type: ignore[assignment]
        # Bridge catches ImportError internally and returns [].
        assert to_function_tools({"hello": lambda: "world"}) == []
    finally:
        if real is not None:
            sys.modules["agents"] = real
        else:
            sys.modules.pop("agents", None)


@pytest.mark.skipif(not _HAS_SDK, reason="openai-agents not installed")
def test_callable_with_matching_name_passes_through() -> None:
    """When `fn.__name__ == registry_key`, no rename is needed — apply
    the decorator directly."""

    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    tools = to_function_tools({"add": add})
    assert len(tools) == 1
    ft = tools[0]
    # FunctionTool / decorated callable exposes `.name`. Surface check —
    # don't assume the internal class name in case the SDK renames it.
    assert getattr(ft, "name", None) == "add"


@pytest.mark.skipif(not _HAS_SDK, reason="openai-agents not installed")
def test_name_override_applied_when_key_differs() -> None:
    """If the registry key differs from the callable's `__name__`, the
    bridge uses `function_tool(name_override=...)` so the SDK exposes
    the registry key."""

    def _internal_impl(x: int) -> int:
        """Doubler."""
        return x * 2

    tools = to_function_tools({"public_double": _internal_impl})
    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "public_double"


@pytest.mark.skipif(not _HAS_SDK, reason="openai-agents not installed")
def test_multiple_tools_preserve_order_and_count() -> None:
    def a() -> str:
        """A."""
        return "a"

    def b() -> str:
        """B."""
        return "b"

    def c() -> str:
        """C."""
        return "c"

    tools = to_function_tools({"a": a, "b": b, "c": c})
    assert len(tools) == 3
    assert [getattr(t, "name", None) for t in tools] == ["a", "b", "c"]
