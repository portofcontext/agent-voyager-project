"""avp-openai-agent — AVP v0.1 agent for the OpenAI Agents SDK.

Observer pattern: the SDK owns its loop; this package subclasses
RunHooks and translates lifecycle callbacks into AVP v0.1 events.
"""

from avp_openai_agent.discovery import Environment, discover_environment
from avp_openai_agent.local_tools_bridge import to_function_tools
from avp_openai_agent.traced_client import (
    TracedOpenAIRunner,
    traced_openai_runner,
)
from avp_openai_agent.translator import (
    OPENAI_AGENTS_SDK_BUILTIN_TOOLS,
    OpenAIAgentTranslator,
)

__version__ = "0.1.0"

# Imported after __version__ because descriptor() reads it.
from avp_openai_agent.descriptor import descriptor

__all__ = [
    "OPENAI_AGENTS_SDK_BUILTIN_TOOLS",
    "Environment",
    "OpenAIAgentTranslator",
    "TracedOpenAIRunner",
    "__version__",
    "descriptor",
    "discover_environment",
    "to_function_tools",
    "traced_openai_runner",
]
