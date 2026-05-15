"""Descriptor shape and identity with `agent_described` event payload."""

from __future__ import annotations

from avp_openai_agent import __version__, descriptor
from avp_openai_agent.translator import OPENAI_AGENTS_SDK_BUILTIN_TOOLS

from avp import T_AGENT_DESCRIBED


def test_descriptor_shape() -> None:
    d = descriptor()
    assert d.agent_name == "avp-openai-agent"
    assert d.agent_version == __version__
    assert d.avp_spec_version == "0.1"
    # The Agents SDK doesn't compile in a default model.
    assert d.default_model is None
    # Supported globs cover both Chat-style and o-series ids.
    assert "gpt-*" in d.supported_models
    assert "o*" in d.supported_models
    # Every hosted-tool catalog entry surfaces as a built_in_tool.
    names = [t.name for t in (d.built_in_tools or [])]
    assert set(names) == set(OPENAI_AGENTS_SDK_BUILTIN_TOOLS)
    for t in d.built_in_tools or []:
        # AVP v0.1 only allows `mcp_server` / `local`. Hosted tools count
        # as local-dispatched from the agent's POV — see translator notes.
        assert t.avp_dispatch_target == "local"
    assert d.built_in_subagents is None
    assert d.built_in_skills is None
    assert "reasoning" in d.capabilities
    assert "handoffs-as-subagents" in d.capabilities


def test_descriptor_is_pure() -> None:
    """Same call → byte-for-byte identical dump. The Descriptor is the
    contract between `describe` (pre-flight) and `agent_described`
    (runtime emission); drift here breaks supervisor cache equality."""
    a = descriptor().model_dump(by_alias=True, exclude_none=True, mode="json")
    b = descriptor().model_dump(by_alias=True, exclude_none=True, mode="json")
    assert a == b


def test_event_type_constant_present() -> None:
    # Sanity: the event-type constant the translator emits is exported.
    assert T_AGENT_DESCRIBED == "avp.agent_described"
