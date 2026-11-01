"""What the agent has before any Commission.

Pydantic AI is a framework: its agents come with no tools, skills, subagents,
or system prompt, so neither does this one. Its tools come from the
Commission's MCP servers."""

from importlib.metadata import version

from avp.descriptor import AgentDescriptor, ModelPattern

AGENT_NAME = "avp-pydantic-ai"
PROVIDERS = ("anthropic", "google", "openai")
"""The providers this agent runs models at."""


def describe() -> AgentDescriptor:
    return AgentDescriptor(
        avp_version="0.1",
        agent_name=AGENT_NAME,
        agent_version=version(AGENT_NAME),
        supported_models=[ModelPattern(provider=p, id="*") for p in PROVIDERS],
    )
