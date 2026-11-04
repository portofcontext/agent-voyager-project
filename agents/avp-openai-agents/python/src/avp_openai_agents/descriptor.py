"""The framework supplies no built-in tools, skills, or subagents."""

import importlib.util
from importlib.metadata import version

from avp.descriptor import AgentDescriptor, ModelPattern

AGENT_NAME = "avp-openai-agents"


def describe() -> AgentDescriptor:
    providers = [ModelPattern(provider="openai", id="*")]
    if importlib.util.find_spec("litellm") is not None:
        providers += [ModelPattern(provider="anthropic", id="*")]
    return AgentDescriptor(
        avp_version="0.1",
        agent_name=AGENT_NAME,
        agent_version=version(AGENT_NAME),
        supported_models=providers,
    )
