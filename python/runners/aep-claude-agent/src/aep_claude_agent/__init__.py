"""aep-claude-agent — AEP v0.1 runner for the Claude Agent SDK.

Observer pattern: the SDK owns its loop; this package translates its lifecycle
events into AEP v0.1 events.
"""

from aep_claude_agent.discovery import (
    Environment,
    SkillInfo,
    SubagentInfo,
    discover_environment,
)
from aep_claude_agent.local_tools_bridge import to_sdk_mcp_server
from aep_claude_agent.traced_client import TracedClaudeSDKClient, traced_claude_sdk_client
from aep_claude_agent.translator import (
    CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS,
    CLAUDE_CODE_PRESET_TOOLS,
    ClaudeAgentTranslator,
)

__version__ = "0.1.0"

__all__ = [
    "CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS",
    "CLAUDE_CODE_PRESET_TOOLS",
    "ClaudeAgentTranslator",
    "Environment",
    "SkillInfo",
    "SubagentInfo",
    "TracedClaudeSDKClient",
    "__version__",
    "discover_environment",
    "to_sdk_mcp_server",
    "traced_claude_sdk_client",
]
