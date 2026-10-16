"""`AvpCallbackHandler` on a plain LangGraph app (no Deep Agents): a hand-built
model/tools loop over LangGraph's `ToolNode`, a model wrapped in a retry, and
a tool that raises."""

from __future__ import annotations

import asyncio

from conftest import ScriptedModel, reply
from langchain_core.tools import tool
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from avp.pricing import load_default_prices
from avp.recorder import Recorder
from avp.trajectory import StopReason
from avp_deep_agents.callbacks import AvpCallbackHandler


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool
def explode() -> str:
    """Always fails."""
    raise ValueError("kaboom")


def _graph(model: ScriptedModel) -> object:
    bound = model.bind_tools([add, explode]).with_retry(
        stop_after_attempt=2,
        retry_if_exception_type=(ConnectionError,),
        wait_exponential_jitter=False,
    )

    async def call_model(state: MessagesState) -> dict:
        return {"messages": [await bound.ainvoke(state["messages"])]}

    builder = StateGraph(MessagesState)
    builder.add_node("model", call_model)
    builder.add_node("tools", ToolNode([add, explode], handle_tool_errors=True))
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", tools_condition)
    builder.add_edge("tools", "model")
    return builder.compile()


async def _record(model: ScriptedModel) -> list[dict]:
    events: list[dict] = []

    async def sink(event: object) -> None:
        events.append(event.model_dump(mode="json", by_alias=True, exclude_none=True))

    rec = Recorder(sink, provider="openai", prices=load_default_prices())
    await rec.prelude(None, _descriptor())
    await rec.start(request_model="openai/gpt-4o-mini")
    handler = AvpCallbackHandler(rec, request_model="openai/gpt-4o-mini")
    result = await _graph(model).ainvoke({"messages": [("user", "go")]}, {"callbacks": [handler]})
    await rec.stop(StopReason.converged, result["messages"][-1].text)
    return events


def _descriptor() -> object:
    from avp.descriptor import AgentDescriptor

    return AgentDescriptor(agent_name="plain-langgraph", agent_version="0", spec_version="0.1")


def test_handler_records_a_plain_langgraph_app() -> None:
    model = ScriptedModel(
        messages=iter(
            [
                ConnectionError("transient"),  # retried: no turn
                reply(
                    "",
                    ("a", "add", {"a": 1, "b": 2}),
                    ("b", "explode", {}),
                    ("c", "add", {"a": 3, "b": 4}),
                ),
                reply("3 and 7"),
            ]
        )
    )
    events = asyncio.run(_record(model))
    types = [e["type"].removeprefix("avp.") for e in events]
    assert types[types.index("agent_started") + 1 :] == [
        "assistant_message",
        "tool_invoked",
        "tool_invoked",
        "tool_invoked",
        "tool_returned",
        "tool_returned",
        "tool_returned",
        "assistant_message",
        "agent_stopped",
    ]
    turns = [e["data"] for e in events if e["type"] == "avp.assistant_message"]
    assert [t["avp.step"] for t in turns] == [1, 2]
    assert all(t["avp.usage"]["input_tokens"] == 1000 for t in turns)
    assert all(t["avp.cost.source"] == "computed" for t in turns)
    results = {
        e["data"]["avp.tool.call_id"]: e["data"]["avp.tool_result"]
        for e in events
        if e["type"] == "avp.tool_returned"
    }
    assert results["a"]["content"] == "3" and not results["a"]["is_error"]
    assert results["c"]["content"] == "7" and not results["c"]["is_error"]
    assert results["b"]["is_error"] and "kaboom" in results["b"]["content"]
    assert len(model.requests) == 3
