"""What the agent has before any Commission.

Pydantic AI is a framework: its agents come with no tools, skills, subagents,
or system prompt, so neither does this one. Its tools come from the
Commission's MCP servers."""

from importlib.metadata import version

from avp.descriptor import AgentDescriptor, ModelPattern

AGENT_NAME = "avp-pydantic-ai"
PROVIDERS = {
    "anthropic": "pydantic_ai.providers.anthropic:AnthropicProvider",
    "google": "pydantic_ai.providers.google:GoogleProvider",
    "openai": "pydantic_ai.providers.openai:OpenAIProvider",
}
"""The providers this agent runs models at, and the Pydantic AI provider class
for each. `run` builds its model from the same table."""


def describe() -> AgentDescriptor:
    return AgentDescriptor(
        avp_version="0.1",
        agent_name=AGENT_NAME,
        agent_version=version(AGENT_NAME),
        supported_models=[ModelPattern(provider=p, id="*") for p in PROVIDERS],
    )
