"""`agent_started.data.tools` / `subagents` carry the resolved surface.

The translator emits `agent_started` post-`on_agent_start`, when the
SDK's Agent object is available and we can introspect its actual tool
list. Test the merged-view payload:

  - Tools list reflects Agent.tools (hosted + function tools)
  - Tools list filters to Commission.enabled_builtin_tools when no Agent
    object is available (defensive path)
  - Subagents list mirrors Commission.subagents refs
  - gen_ai.operation.name / gen_ai.provider.name / gen_ai.request.model
    are populated on every agent_started
"""

from __future__ import annotations

import asyncio
from typing import Any

from avp_openai_agent import OpenAIAgentTranslator, descriptor

from avp import AgentStartedEvent, Commission


class _FakeAgent:
    def __init__(self, name: str, tools: list[Any] | None = None) -> None:
        self.name = name
        self.tools = tools or []
        self.model = "gpt-5-nano"


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


def _commission(**overrides: Any) -> Commission:
    base: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "test-surface",
        "model": "gpt-5-nano",
        "prompt": "hi",
    }
    base.update(overrides)
    return Commission.model_validate(base)


def _drive_on_agent_start(commission: Commission, agent: _FakeAgent) -> list[Any]:
    captured: list[Any] = []
    t = OpenAIAgentTranslator(commission, on_event=captured.append, descriptor=descriptor())
    t._root_agent_name = agent.name
    asyncio.run(t.on_agent_start(None, agent))
    return captured


def test_agent_started_tools_reflect_agent_tools_list() -> None:
    """When the SDK gave us an Agent, the tool surface mirrors what the
    SDK actually configured — including hosted-tool class names like
    `WebSearchTool` if no `.name` is set, and any function-tool names."""
    agent = _FakeAgent(
        name="avp-agent",
        tools=[_FakeTool("web_search"), _FakeTool("greet")],
    )
    captured = _drive_on_agent_start(_commission(), agent)
    started = next(ev for ev in captured if isinstance(ev, AgentStartedEvent))
    tool_names = [t.name for t in (started.data.tools or [])]
    assert tool_names == ["web_search", "greet"]
    # Hosted-tool dispatch maps to AVP `local` (no `remote` axis in v0.1).
    for t in started.data.tools or []:
        assert t.avp_dispatch_target == "local"


def test_agent_started_tools_filtered_to_allowlist_when_no_agent_object() -> None:
    """If the started hook fires before we have an Agent object (i.e.
    `agent=None`), the translator falls back to the Commission allowlist
    intersected with the bundled builtin-tool catalog. Verifies the
    defensive path is honest — only known builtin names survive."""
    commission = _commission(enabled_builtin_tools=["web_search", "not_a_real_tool"])
    captured: list[Any] = []
    t = OpenAIAgentTranslator(commission, on_event=captured.append, descriptor=descriptor())
    t._emit_agent_started(agent=None)
    started = next(ev for ev in captured if isinstance(ev, AgentStartedEvent))
    tool_names = [t.name for t in (started.data.tools or [])]
    assert tool_names == ["web_search"]


def test_agent_started_subagents_from_commission_refs() -> None:
    commission = _commission(
        subagents=[
            {"id": "researcher", "ref": "x://researcher"},
            {"id": "writer", "ref": "x://writer"},
        ]
    )
    agent = _FakeAgent(name="avp-agent")
    captured = _drive_on_agent_start(commission, agent)
    started = next(ev for ev in captured if isinstance(ev, AgentStartedEvent))
    names = [s.name for s in (started.data.subagents or [])]
    assert names == ["researcher", "writer"]


def test_agent_started_otel_attributes_populated() -> None:
    """Every agent_started MUST carry gen_ai.operation.name +
    gen_ai.provider.name (OpenTelemetry GenAI convention) and the
    requested model when Commission.model is set."""
    commission = _commission(model="gpt-5-nano")
    agent = _FakeAgent(name="avp-agent")
    captured = _drive_on_agent_start(commission, agent)
    started = next(ev for ev in captured if isinstance(ev, AgentStartedEvent))
    assert started.data.gen_ai_operation_name == "invoke_agent"
    assert started.data.gen_ai_provider_name == "openai"
    assert started.data.gen_ai_request_model == "gpt-5-nano"


def test_agent_started_only_fires_once_for_root() -> None:
    """on_agent_start fires once per agent the SDK starts (root + every
    handoff target). agent_started is a per-run lifecycle marker, so we
    suppress the duplicate for handoff targets."""
    commission = _commission()
    captured: list[Any] = []
    t = OpenAIAgentTranslator(commission, on_event=captured.append, descriptor=descriptor())
    t._root_agent_name = "root"
    asyncio.run(t.on_agent_start(None, _FakeAgent(name="root")))
    asyncio.run(t.on_agent_start(None, _FakeAgent(name="researcher")))
    starts = [ev for ev in captured if isinstance(ev, AgentStartedEvent)]
    assert len(starts) == 1
