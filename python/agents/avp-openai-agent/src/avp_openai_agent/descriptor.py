"""Agent Descriptor for avp-openai-agent.

Surfaced in two places that MUST agree:

  - `avp-openai-agent describe` prints `descriptor()` as JSON to stdout.
  - The `agent_described` event the translator emits between
    `run_requested` and `agent_started` carries the same payload.

Scope: hosted-tool catalog the OpenAI Agents SDK ships out of the box.
User-defined function tools and Commission-managed subagents/skills are
not statically enumerable; they appear on `agent_started` (merged view)
or on managed-ref events.
"""

from __future__ import annotations

from typing import Any

from avp import AgentDescriptor
from avp_openai_agent.translator import OPENAI_AGENTS_SDK_BUILTIN_TOOLS

# Features this agent advertises:
#
# - `reasoning`: reasoning items from o-series / gpt-5 are parsed and
#   emitted as `reasoning_emitted` (text or redacted).
# - `handoffs-as-subagents`: OpenAI Agents SDK handoffs (control
#   transfers) are surfaced on the AVP wire as subagent_invoked /
#   subagent_returned pairs. Strict consumers should note the
#   semantic stretch: handoffs are not function-call style returns.
# - `hosted-tools`: web_search / file_search / code_interpreter /
#   computer_use / image_generation / local_shell run on OpenAI
#   infrastructure (avp.tool.dispatch_target = "remote").
_CAPABILITIES = (
    "reasoning",
    "handoffs-as-subagents",
    "hosted-tools",
)


def descriptor() -> AgentDescriptor:
    """Build the AgentDescriptor for this agent build.

    Pure: no I/O, no env reads, no filesystem walks. Same input always
    yields the same output for a given installed version of
    `avp-openai-agent`.
    """
    from avp_openai_agent import __version__

    built_in_tools: list[dict[str, Any]] = [
        {"name": name, "avp.dispatch_target": "local"} for name in OPENAI_AGENTS_SDK_BUILTIN_TOOLS
    ]

    return AgentDescriptor.model_validate(
        {
            "agent_name": "avp-openai-agent",
            "agent_version": __version__,
            "avp_spec_version": "0.1",
            # The SDK doesn't compile in a default model. The Agents SDK
            # falls back to its own default; commissioning code picks
            # explicitly. Honest-null.
            "default_model": None,
            # The OpenAI Agents SDK supports OpenAI's GPT / o-series
            # natively. With OPENAI_BASE_URL overridden it can speak to
            # OpenAI-compatible backends (Together, OpenRouter, Ollama,
            # …); we don't enumerate those globs here.
            "supported_models": ["gpt-*", "o*"],
            "built_in_tools": built_in_tools,
            "built_in_subagents": None,
            "built_in_skills": None,
            "capabilities": list(_CAPABILITIES),
        }
    )


__all__ = ["descriptor"]
