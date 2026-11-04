"""The pinned Claude Code profile, captured from its native model request."""

import json
from functools import cache
from importlib.metadata import version
from importlib.resources import files

from avp.descriptor import AgentDescriptor, ModelPattern

AGENT_NAME = "avp-claude-agent-sdk"
CLAUDE_VERSION = "2.1.303"


@cache
def describe() -> AgentDescriptor:
    catalog = json.loads(files("avp_claude_agent_sdk").joinpath("catalog.json").read_text())
    return AgentDescriptor(
        avp_version="0.1",
        agent_name=AGENT_NAME,
        agent_version=version(AGENT_NAME),
        supported_models=[ModelPattern(provider="anthropic", id="claude-*")],
        tools=catalog["tools"],
        skills=catalog["skills"],
        subagents=catalog["subagents"],
    )
