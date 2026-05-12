"""avp-claude-agent — AVP v0.1 agent for the Claude Agent SDK.

Observer pattern: the SDK owns its loop; this package translates its lifecycle
events into AVP v0.1 events.
"""

from avp_claude_agent.builtin_tools import (
    CLAUDE_CODE_BUILTIN_TOOL_CATALOG,
    CLAUDE_CODE_PRESET_TOOLS,
)
from avp_claude_agent.discovery import (
    Environment,
    SkillInfo,
    SubagentInfo,
    discover_environment,
)
from avp_claude_agent.local_tools_bridge import to_sdk_mcp_server
from avp_claude_agent.traced_client import TracedClaudeSDKClient, traced_claude_sdk_client
from avp_claude_agent.translator import (
    CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS,
    ClaudeAgentTranslator,
)

__version__ = "0.1.0"

# Imported after __version__ because descriptor() reads it.
from avp_claude_agent.descriptor import descriptor

__all__ = [
    "CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS",
    "CLAUDE_CODE_BUILTIN_TOOL_CATALOG",
    "CLAUDE_CODE_PRESET_TOOLS",
    "ClaudeAgentTranslator",
    "Environment",
    "SkillInfo",
    "SubagentInfo",
    "TracedClaudeSDKClient",
    "__version__",
    "descriptor",
    "discover_environment",
    "to_sdk_mcp_server",
    "traced_claude_sdk_client",
]
