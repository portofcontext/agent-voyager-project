"""LocalTools — a generic ToolDriver for in-process Python callables.

The Claude Agent SDK has `@tool` and `create_sdk_mcp_server()` for tools
that run inside the SDK process. AVP's equivalent is this driver: a
runtime registry of named callables that the reference agent
dispatches via the existing `ToolDriver` protocol — no wire changes,
no special-casing in `agent.py`.

Design points:

  - Wire-pure Commission. Python callables can't go in `Commission.tools[]`
    (that's JSON). LocalTools is a runtime binding; users register
    callables at startup and pass the `LocalTools` instance to
    `AVPAgent(tools=...)`.
  - Composition over special-casing. LocalTools accepts a `fallback`
    ToolDriver so users can mix their callables with a agent's
    built-ins (e.g. `ShellTools` from avp-anthropic): callables
    LocalTools knows about win, everything else falls through.
  - Schemas exported. `.schemas` returns the `{name, description,
    input_schema}` list agents hand to the model so it can call them.
    Same shape as `avp_anthropic.shell_tools.SHELL_TOOL_SCHEMAS`.

Two registration styles:

    tools = LocalTools()

    # 1) Direct register
    tools.register(
        "calculate",
        lambda inp: {"result": inp["a"] + inp["b"]},
        description="Add two numbers.",
        input_schema={
            "type": "object",
            "required": ["a", "b"],
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        },
    )

    # 2) Decorator
    @tools.tool(
        description="Add two numbers.",
        input_schema={"type": "object", ...},
    )
    def calculate(input: dict) -> dict:
        return {"result": input["a"] + input["b"]}

Return-value handling: the callable can return a `ToolOutcome` (full
control over text/structured/error/duration), a string (becomes
`output`), or any JSON-serializable value (becomes
`output`+`output_json`). Exceptions become `ToolOutcome(error=...)` so
a buggy tool doesn't take down the run.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from avp.agent.drivers import ToolDriver, ToolOutcome

ToolFn = Callable[[dict[str, Any]], Any]


class LocalTools(ToolDriver):
    """Runtime registry of in-process Python tools.

    Compose with a fallback `ToolDriver` (e.g. `ShellTools`) to layer
    user-defined tools over agent built-ins:

        tools = LocalTools(fallback=ShellTools())

    The agent sees a single `ToolDriver`. LocalTools' callables win
    by name; everything else routes to the fallback (and ultimately to
    supervisor RPC if no driver claims it via `is_local`).
    """

    def __init__(self, *, fallback: ToolDriver | None = None) -> None:
        self._handlers: dict[str, ToolFn] = {}
        self._schemas: dict[str, dict[str, Any]] = {}
        self._fallback = fallback

    # ── Registration ─────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        fn: ToolFn,
        *,
        description: str,
        input_schema: dict[str, Any],
    ) -> None:
        """Register a callable as a local tool.

        `name` is what the model calls. `description` is what the model
        sees in its tools[] list; `input_schema` is JSON Schema (same
        shape MCP tools use). The callable receives the validated input
        dict and returns one of: ToolOutcome | str | JSON-serializable
        value (see module docstring for return-value handling).

        Re-registering an existing name overwrites the previous binding
        — useful for hot-reload during development; surprising in
        production. Don't do it unless you mean to.
        """
        if not name:
            raise ValueError("LocalTools.register: name must be non-empty")
        self._handlers[name] = fn
        self._schemas[name] = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
        }

    def tool(
        self,
        *,
        description: str,
        input_schema: dict[str, Any],
        name: str | None = None,
    ) -> Callable[[ToolFn], ToolFn]:
        """Decorator form. Defaults `name` to the function's `__name__`.

        @tools.tool(description="...", input_schema={...})
        def my_tool(input: dict) -> str:
            ...
        """

        def decorator(fn: ToolFn) -> ToolFn:
            self.register(
                name or fn.__name__,
                fn,
                description=description,
                input_schema=input_schema,
            )
            return fn

        return decorator

    # ── Schema export ────────────────────────────────────────────────────

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """The `[{name, description, input_schema}]` list to hand to a
        agent's tool-surface builder so the model knows about these
        tools. For avp-anthropic, pass to
        `build_anthropic_tools(config, builtins=...)`. Combines with a
        fallback's schemas if the fallback exposes them."""
        out = list(self._schemas.values())
        fallback_schemas = getattr(self._fallback, "schemas", None)
        if isinstance(fallback_schemas, list):
            # Fallback wins for names we don't define — same precedence
            # as is_local / invoke below.
            ours = {s["name"] for s in out}
            out.extend(s for s in fallback_schemas if s.get("name") not in ours)
        return out

    @property
    def names(self) -> list[str]:
        return list(self._handlers.keys())

    def entries(self) -> list[tuple[str, ToolFn, dict[str, Any]]]:
        """Public iterator over registered tools.

        Yields `(name, callable, schema)` tuples where `schema` is the
        `{name, description, input_schema}` dict the tool was registered
        with. Used by bridges to other runtimes (e.g. converting a
        LocalTools registry into a Claude Agent SDK in-process MCP
        server) without poking at private attributes.
        """
        return [(name, self._handlers[name], dict(self._schemas[name])) for name in self._handlers]

    # ── ToolDriver protocol ──────────────────────────────────────────────

    def is_local(self, tool: str) -> bool:
        if tool in self._handlers:
            return True
        return self._fallback.is_local(tool) if self._fallback is not None else False

    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome:
        fn = self._handlers.get(tool)
        if fn is None:
            if self._fallback is not None:
                return self._fallback.invoke(tool, input)
            return ToolOutcome(error=f"LocalTools: unknown tool {tool!r}")
        return _invoke(fn, input)


def _invoke(fn: ToolFn, input: dict[str, Any]) -> ToolOutcome:
    """Call the user's tool function and coerce its return value to a
    `ToolOutcome`. Exceptions are caught and surfaced as the outcome's
    `error` field — a buggy tool produces a `tool_failed` event but
    doesn't take down the run.

    Return-value coercion:
      - `ToolOutcome` → returned verbatim (full control).
      - `str` → `ToolOutcome(output=<str>)`.
      - `None` → `ToolOutcome(output="")`.
      - anything else → JSON-coerced into `output` (text) +
        `output_json` (structured) so consumers get both shapes.
    """
    t0 = time.monotonic()
    try:
        result = fn(input)
    except Exception as exc:
        return ToolOutcome(
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.monotonic() - t0) * 1000) or 1,
        )
    duration_ms = int((time.monotonic() - t0) * 1000) or 1

    if isinstance(result, ToolOutcome):
        # Caller handed us a fully-formed outcome — preserve their
        # duration if set, otherwise stamp ours.
        if result.duration_ms == 1:
            result.duration_ms = duration_ms
        return result
    if result is None:
        return ToolOutcome(output="", duration_ms=duration_ms)
    if isinstance(result, str):
        return ToolOutcome(output=result, duration_ms=duration_ms)
    # JSON-coerce. Surface both representations so wire consumers
    # see structured output AND a text rendering for the model.
    try:
        rendered = json.dumps(result, default=str)
    except (TypeError, ValueError):
        rendered = repr(result)
    return ToolOutcome(
        output=rendered,
        output_json=result if _is_json_native(result) else None,
        duration_ms=duration_ms,
    )


def _is_json_native(value: Any) -> bool:
    """True if `value` is a primitive JSON-natively-serializable type.
    Used to decide whether to stash `output_json` — we don't want to
    surface random Python objects (datetime, dataclass, etc.) as
    'structured' just because we coerced them via `default=str`."""
    return isinstance(value, dict | list | bool | int | float | str) or value is None
