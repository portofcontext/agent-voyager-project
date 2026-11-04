"""Read the native graph and filesystem middleware's shipped capabilities."""

from functools import cache
from importlib.metadata import version

from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.utils.function_calling import convert_to_openai_tool

from avp.descriptor import AgentDescriptor, ModelPattern, Subagent, Tool
from avp_deep_agents import commission as cm


def declaration(tool, server=None):
    schema = convert_to_openai_tool(tool)["function"]["parameters"]
    return Tool(
        name=tool.name, description=tool.description, inputSchema=schema, mcp_server_id=server
    )


def graph_tools(graph):
    return dict(graph.nodes["tools"].bound.tools_by_name)


@cache
def describe():
    backend = cm.backend()
    graph = cm.build(GenericFakeChatModel(messages=iter(())), backend)
    return AgentDescriptor(
        avp_version="0.1",
        agent_name=cm.AGENT_NAME,
        agent_version=version(cm.AGENT_NAME),
        supported_models=[ModelPattern(provider=p, id="*") for p in cm.PROVIDERS],
        tools=[declaration(t) for t in graph_tools(graph).values()],
        subagents=[
            Subagent(
                name=GENERAL_PURPOSE_SUBAGENT["name"],
                description=GENERAL_PURPOSE_SUBAGENT["description"],
                tools=[declaration(t) for t in FilesystemMiddleware(backend=backend).tools],
            )
        ],
    )
