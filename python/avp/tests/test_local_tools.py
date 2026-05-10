"""LocalTools — generic ToolDriver for in-process Python callables.

This is the AVP equivalent of Claude Agent SDK's `@tool` /
`create_sdk_mcp_server()` pattern: users register named callables at
runtime; the reference agent dispatches them like any other local tool
(no wire changes, no special-casing in `agent.py`).

Tests cover:
  - Direct register + decorator forms
  - Return-value coercion (ToolOutcome | str | dict | None | exception)
  - Composition with a fallback ToolDriver
  - End-to-end: registered callable runs, emits tool_invoked + tool_returned
  - End-to-end: composition with ScriptedTools as fallback
"""

from __future__ import annotations

from typing import Any

from avp import Commission
from avp.agent.agent import AVPAgent
from avp.agent.drivers import ModelResponse, ScriptedToolCall, ToolOutcome
from avp.agent.local_tools import LocalTools
from avp.agent.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from avp.types import (
    ToolFailedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)


def _by_type(traj, type_):
    return [e for e in traj if isinstance(e, type_)]


# ── Registration ───────────────────────────────────────────────────────────


def test_direct_register_makes_tool_local() -> None:
    tools = LocalTools()
    tools.register(
        "add",
        lambda inp: {"sum": inp["a"] + inp["b"]},
        description="Add two numbers.",
        input_schema={
            "type": "object",
            "required": ["a", "b"],
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        },
    )
    assert tools.is_local("add")
    assert "add" in tools.names


def test_decorator_register_uses_function_name_by_default() -> None:
    tools = LocalTools()

    @tools.tool(description="echo input", input_schema={"type": "object"})
    def echo(input: dict[str, Any]) -> str:
        return str(input)

    assert tools.is_local("echo")


def test_decorator_register_can_override_name() -> None:
    tools = LocalTools()

    @tools.tool(name="custom_name", description="x", input_schema={"type": "object"})
    def fn(input: dict[str, Any]) -> str:
        return ""

    assert tools.is_local("custom_name")
    assert not tools.is_local("fn")


def test_register_empty_name_raises() -> None:
    tools = LocalTools()
    try:
        tools.register("", lambda i: "", description="x", input_schema={})
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty name")


# ── Return-value coercion ──────────────────────────────────────────────────


def test_string_return_becomes_output_text() -> None:
    tools = LocalTools()
    tools.register("s", lambda i: "hello", description="x", input_schema={})
    out = tools.invoke("s", {})
    assert out.output == "hello"
    assert out.error is None


def test_none_return_becomes_empty_output() -> None:
    tools = LocalTools()
    tools.register("n", lambda i: None, description="x", input_schema={})
    out = tools.invoke("n", {})
    assert out.output == ""
    assert out.error is None


def test_dict_return_is_json_coerced_with_structured() -> None:
    """Dict / list returns get rendered to JSON (text) AND surfaced as
    `output_json` (structured) so wire consumers see both shapes —
    text for the model, structured for audit pipelines."""
    tools = LocalTools()
    tools.register("d", lambda i: {"k": "v", "n": 1}, description="x", input_schema={})
    out = tools.invoke("d", {})
    assert out.output_json == {"k": "v", "n": 1}
    # JSON text is deterministic for a flat dict.
    assert '"k": "v"' in out.output


def test_tool_outcome_return_passes_through() -> None:
    """Callers that need full control (custom duration, structured
    output, rejection flag) can return a ToolOutcome directly — we
    don't wrap or rewrite it."""
    tools = LocalTools()
    tools.register(
        "raw",
        lambda i: ToolOutcome(output="x", output_json={"k": 1}, duration_ms=42),
        description="x",
        input_schema={},
    )
    out = tools.invoke("raw", {})
    assert out.output == "x"
    assert out.output_json == {"k": 1}
    assert out.duration_ms == 42


def test_exception_in_callable_becomes_error_outcome() -> None:
    """A buggy tool produces a `tool_failed` event but doesn't take
    down the run. Exception class + message land in `error`."""
    tools = LocalTools()

    def boom(_: dict[str, Any]) -> str:
        raise RuntimeError("boom")

    tools.register("boom", boom, description="x", input_schema={})
    out = tools.invoke("boom", {})
    assert out.error is not None
    assert "RuntimeError" in out.error
    assert "boom" in out.error


def test_unknown_tool_returns_error() -> None:
    tools = LocalTools()
    out = tools.invoke("missing", {})
    assert out.error is not None
    assert "missing" in out.error


# ── Composition with a fallback driver ─────────────────────────────────────


def test_fallback_driver_handles_unregistered_tools() -> None:
    """Local-first: a tool LocalTools knows about wins. Anything else
    falls through to the fallback driver. Lets users layer their own
    callables over agent built-ins like ShellTools."""
    fallback = ScriptedTools({"shellish": {"output": "from-fallback"}})
    tools = LocalTools(fallback=fallback)
    tools.register("local", lambda i: "from-local", description="x", input_schema={})

    assert tools.is_local("local")
    assert tools.is_local("shellish")
    assert not tools.is_local("nope")

    assert tools.invoke("local", {}).output == "from-local"
    assert tools.invoke("shellish", {}).output == "from-fallback"


def test_local_wins_over_fallback_on_name_collision() -> None:
    """If the user registers a name the fallback also knows about,
    LocalTools' callable wins. Lets users override built-ins."""
    fallback = ScriptedTools({"both": {"output": "from-fallback"}})
    tools = LocalTools(fallback=fallback)
    tools.register("both", lambda i: "from-local", description="x", input_schema={})
    assert tools.invoke("both", {}).output == "from-local"


def test_schemas_property_combines_local_and_fallback_schemas() -> None:
    """When the fallback exposes a `.schemas` list (e.g. ShellTools
    style), LocalTools.schemas returns the merged list — local first,
    then fallback entries we don't shadow. Lets the agent declare
    everything to the model in one shot."""

    class _Fallback:
        @property
        def schemas(self) -> list[dict[str, Any]]:
            return [{"name": "fallback_only", "description": "fb", "input_schema": {}}]

        def is_local(self, tool: str) -> bool:
            return tool == "fallback_only"

        def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome:
            return ToolOutcome(output="fb")

    tools = LocalTools(fallback=_Fallback())
    tools.register("local_only", lambda i: "x", description="lo", input_schema={})

    names = [s["name"] for s in tools.schemas]
    assert "local_only" in names
    assert "fallback_only" in names


# ── End-to-end with AVPAgent ──────────────────────────────────────────────


def _model_calling(tool: str, *, call_id: str = "c1") -> ScriptedModel:
    return ScriptedModel(
        [
            ModelResponse(
                tokens_input=10,
                tokens_output=5,
                cost_usd=0.0001,
                duration_ms=1,
                tool_calls=[ScriptedToolCall(call_id=call_id, tool=tool, input={"x": 1})],
                converged=False,
            ),
            ModelResponse(
                tokens_input=5,
                tokens_output=3,
                cost_usd=0.0001,
                duration_ms=1,
                text="done",
                converged=True,
            ),
        ]
    )


def test_agent_dispatches_local_tool_and_emits_full_lifecycle() -> None:
    """End-to-end: registered callable is invoked, tool_invoked +
    tool_returned both fire, the model sees the output via the
    next-turn history, run converges normally."""
    tools = LocalTools()
    tools.register("greet", lambda inp: f"hi {inp['x']}", description="x", input_schema={})

    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="lt-e2e", model="test/mock"),
        model=_model_calling("greet"),
        tools=tools,
        supervisor=ScriptedSupervisor(),
    )
    agent.run()

    invoked = _by_type(agent.trajectory, ToolInvokedEvent)
    returned = _by_type(agent.trajectory, ToolReturnedEvent)
    assert len(invoked) == 1
    assert len(returned) == 1
    assert returned[0].data.avp_tool_result_text == "hi 1"
    # No tool_failed.
    assert not _by_type(agent.trajectory, ToolFailedEvent)


def test_agent_routes_local_tool_with_fallback_to_correct_handler() -> None:
    """LocalTools + ScriptedTools fallback: the model calls a LOCAL
    name → LocalTools handles it. The model could call a fallback
    name on the next turn → ScriptedTools handles it. Same wire shape;
    the agent doesn't know which side dispatched."""
    fallback = ScriptedTools({"shellish": {"output": "shell-output"}})
    tools = LocalTools(fallback=fallback)
    tools.register("calc", lambda inp: {"r": 42}, description="x", input_schema={})

    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="lt-mixed", model="test/mock"),
        model=_model_calling("calc"),
        tools=tools,
        supervisor=ScriptedSupervisor(),
    )
    agent.run()
    returned = _by_type(agent.trajectory, ToolReturnedEvent)[0]
    # The dict return was JSON-coerced for the result text.
    assert '"r": 42' in returned.data.avp_tool_result_text


def test_local_tool_exception_emits_tool_failed_not_tool_returned() -> None:
    """Buggy tool → tool_failed event, run continues. The model sees
    the error in history and can adapt on the next turn."""
    tools = LocalTools()

    def explode(_: dict[str, Any]) -> str:
        raise ValueError("nope")

    tools.register("explode", explode, description="x", input_schema={})

    agent = AVPAgent(
        commission=Commission(schema_version="0.1", run_id="lt-fail", model="test/mock"),
        model=_model_calling("explode"),
        tools=tools,
        supervisor=ScriptedSupervisor(),
    )
    agent.run()

    failed = _by_type(agent.trajectory, ToolFailedEvent)
    assert len(failed) == 1
    assert "ValueError" in failed[0].data.avp_tool_error
    assert not _by_type(agent.trajectory, ToolReturnedEvent)
