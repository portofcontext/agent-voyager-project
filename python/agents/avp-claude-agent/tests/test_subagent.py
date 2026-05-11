"""Subagent dispatch tests for ClaudeAgentTranslator.

The Claude Agent SDK exposes a parent's subagent invocation as a single
`Agent` tool_use → tool_result pair (per CASDK research; subagent
internals are opaque to the parent's observer surface). This translator
diverts that pair into AVP's `subagent_invoked` / `subagent_returned`
lifecycle so consumers see one consistent wire shape across agents
(driver-pattern avp-anthropic produces the rich nested-tree variant; this
agent produces the thin invoked+returned variant — same events, just
without internals).

These tests pin:
  - Commission.subagents → ClaudeAgentOptions.agents translation
  - PreToolUse on an `Agent` tool with declared subagent_type emits
    subagent_invoked, NOT tool_invoked
  - PostToolUse for the matched call emits subagent_returned, NOT
    tool_returned
  - Frame span_id pairs across invoked/returned
  - The `Agent` tool with an UNDECLARED subagent_type falls through as a
    regular tool (we don't accidentally swallow non-AVP Agent calls)
  - The `subagent_type` field is stripped from `avp.subagent.input` so
    the recorded input matches what the parent meant to pass
  - Subagents appear on `agent_started.data.subagents` for consumers
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from avp import (
    AgentStartedEvent,
    Commission,
    SubagentInvokedEvent,
    SubagentRef,
    SubagentReturnedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
from avp_claude_agent import ClaudeAgentTranslator


@dataclass
class _FakeOptions:
    kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@dataclass
class _FakeHookMatcher:
    matcher: str | None
    hooks: list


@dataclass
class _FakeAgentDefinition:
    """Stand-in for `claude_agent_sdk.AgentDefinition` — captures every kwarg
    the translator passed in so tests can assert the mapping without depending
    on the real SDK class shape."""

    payload: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        self.payload = kwargs


def _make_translator(cfg: Commission) -> tuple[ClaudeAgentTranslator, list]:
    out: list = []
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
        sdk_agent_definition_cls=_FakeAgentDefinition,
    )
    return t, out


def _cfg_with_subagent(**overrides: Any) -> Commission:
    base: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "t-sa",
        "model": "claude-sonnet-4-6",
        "prompt": "kick off",
        "subagents": [SubagentRef(id="researcher", ref="sk_researcher_v1")],
    }
    base.update(overrides)
    return Commission(**base)


def _by_type(events: list, type_: type) -> list:
    return [e for e in events if isinstance(e, type_)]


def test_managed_subagent_refs_translate_to_sdk_agents_after_resolution() -> None:
    """The translator's `_build_sdk_agents` consumes resolved metadata
    from `_resolved_subagents` and produces a ClaudeAgentOptions.agents
    dict keyed by Commission.subagents[].id. Without resolution,
    `_resolved_subagents` is empty so the entry surfaces with a minimal
    payload (the SDK uses its defaults)."""
    cfg = _cfg_with_subagent()
    t, _ = _make_translator(cfg)
    # Pre-populate resolved metadata as if `avp.resolve` had run.
    t._resolved_subagents = {
        "researcher": {
            "description": "Looks things up.",
            "system_prompt": "You are a researcher.",
        }
    }
    opts = t._build_sdk_options()
    agents = opts.kwargs.get("agents")
    assert agents is not None
    assert "researcher" in agents
    assert agents["researcher"].payload["description"] == "Looks things up."
    assert agents["researcher"].payload["prompt"] == "You are a researcher."


def test_no_subagents_yields_no_agents_kwarg() -> None:
    """Backwards-compat: a Commission without subagents MUST NOT populate
    options.agents (so existing setups that assume the SDK uses its
    filesystem-loaded agents continue to work)."""
    cfg = Commission(schema_version="0.1", run_id="t", model="claude-sonnet-4-6")
    t, _ = _make_translator(cfg)
    opts = t._build_sdk_options()
    assert "agents" not in opts.kwargs


def test_pre_tool_use_on_agent_with_declared_subagent_emits_subagent_invoked() -> None:
    cfg = _cfg_with_subagent()
    t, out = _make_translator(cfg)

    asyncio.run(
        t._on_pre_tool_use_hook(
            {
                "tool_use_id": "tu-1",
                "tool_name": "Agent",
                "tool_input": {
                    "subagent_type": "researcher",
                    "prompt": "find auth handlers",
                },
            },
            None,
            None,
        )
    )

    invoked = _by_type(out, SubagentInvokedEvent)
    tool_invoked = _by_type(out, ToolInvokedEvent)
    assert len(invoked) == 1, "subagent_invoked MUST be emitted for declared subagents"
    assert not tool_invoked, "tool_invoked MUST NOT be emitted for subagent dispatch"
    ev = invoked[0]
    assert ev.data.gen_ai_agent_name == "researcher"
    # SubagentRef carries no description; resolver-supplied metadata is the
    # source of truth (and not threaded into the translator's SDK-hook path).
    assert ev.data.gen_ai_agent_description is None
    # The SDK-internal `subagent_type` discriminator is stripped — the
    # AVP wire records what the parent agent meant to pass.
    assert ev.data.avp_subagent_input == {"prompt": "find auth handlers"}


def test_post_tool_use_for_subagent_emits_subagent_returned() -> None:
    cfg = _cfg_with_subagent()
    t, out = _make_translator(cfg)

    asyncio.run(
        t._on_pre_tool_use_hook(
            {
                "tool_use_id": "tu-2",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "researcher", "prompt": "go"},
            },
            None,
            None,
        )
    )
    asyncio.run(
        t._on_post_tool_use_hook(
            {
                "tool_use_id": "tu-2",
                "tool_name": "Agent",
                "tool_response": "found 3 handlers in src/auth/",
            },
            None,
            None,
        )
    )

    returned = _by_type(out, SubagentReturnedEvent)
    tool_returned = _by_type(out, ToolReturnedEvent)
    assert len(returned) == 1
    assert not tool_returned, "tool_returned MUST NOT be emitted for subagent dispatch"
    assert returned[0].data.avp_subagent_result_text == "found 3 handlers in src/auth/"


def test_subagent_invoked_and_returned_share_frame_span_id() -> None:
    """Frame pairing — the load-bearing invariant for nested span tree
    reconstruction. If this drifts, consumers can't pair invocations to
    their results, and AVP's wire shape stops being a tree."""
    cfg = _cfg_with_subagent()
    t, out = _make_translator(cfg)

    asyncio.run(
        t._on_pre_tool_use_hook(
            {
                "tool_use_id": "tu-3",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "researcher", "prompt": "go"},
            },
            None,
            None,
        )
    )
    asyncio.run(
        t._on_post_tool_use_hook(
            {"tool_use_id": "tu-3", "tool_name": "Agent", "tool_response": "ok"},
            None,
            None,
        )
    )

    inv = _by_type(out, SubagentInvokedEvent)[0]
    ret = _by_type(out, SubagentReturnedEvent)[0]
    assert inv.data.span_id == ret.data.span_id


def test_agent_tool_with_undeclared_subagent_falls_through_as_tool() -> None:
    """Safety: only a tool_use whose `subagent_type` matches a declared AVP
    subagent diverts. An `Agent` tool_use the SDK might surface for some
    other reason (filesystem-defined subagent, external) MUST still be
    surfaced as a regular tool_invoked so it doesn't disappear from the
    trajectory."""
    cfg = _cfg_with_subagent()  # only `researcher` is declared
    t, out = _make_translator(cfg)

    asyncio.run(
        t._on_pre_tool_use_hook(
            {
                "tool_use_id": "tu-4",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "not-declared", "prompt": "go"},
            },
            None,
            None,
        )
    )

    assert not _by_type(out, SubagentInvokedEvent)
    tool_invoked = _by_type(out, ToolInvokedEvent)
    assert len(tool_invoked) == 1
    assert tool_invoked[0].data.gen_ai_tool_name == "Agent"


def test_subagents_appear_in_agent_started_data() -> None:
    cfg = _cfg_with_subagent()
    t, out = _make_translator(cfg)
    t._emit_agent_started()
    started = _by_type(out, AgentStartedEvent)[0]
    assert started.data.subagents is not None
    names = {sa.name for sa in started.data.subagents}
    # Commission ref's id plus the SDK built-in (general-purpose).
    assert names == {"researcher", "general-purpose"}
    # Description is honest-null at agent_started — comes from the resolver.
    assert next(sa for sa in started.data.subagents if sa.name == "researcher").description is None


def test_subagent_helper_handles_multiple_invocations_in_sequence() -> None:
    """Two sequential subagent calls each get their own frame span and
    invocation_id — and the second invocation's PostToolUse correctly
    pairs to the second's PreToolUse (not the first's)."""
    cfg = _cfg_with_subagent()
    t, out = _make_translator(cfg)

    for tu_id, prompt in [("tu-a", "first"), ("tu-b", "second")]:
        asyncio.run(
            t._on_pre_tool_use_hook(
                {
                    "tool_use_id": tu_id,
                    "tool_name": "Agent",
                    "tool_input": {"subagent_type": "researcher", "prompt": prompt},
                },
                None,
                None,
            )
        )
        asyncio.run(
            t._on_post_tool_use_hook(
                {"tool_use_id": tu_id, "tool_name": "Agent", "tool_response": f"ok-{prompt}"},
                None,
                None,
            )
        )

    invoked = _by_type(out, SubagentInvokedEvent)
    returned = _by_type(out, SubagentReturnedEvent)
    assert len(invoked) == 2 and len(returned) == 2
    # Each pair shares its own frame.
    assert invoked[0].data.span_id == returned[0].data.span_id
    assert invoked[1].data.span_id == returned[1].data.span_id
    # The two pairs are distinct frames.
    assert invoked[0].data.span_id != invoked[1].data.span_id
    # Distinct invocation_ids.
    assert invoked[0].data.avp_subagent_invocation_id != invoked[1].data.avp_subagent_invocation_id
