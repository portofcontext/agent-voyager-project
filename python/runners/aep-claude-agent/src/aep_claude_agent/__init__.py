"""aep-claude-agent — AEP v0.1 runner for the Claude Agent SDK.

Observer pattern: the SDK owns its loop; this package translates its lifecycle
events into AEP v0.1 events.
"""

from aep_claude_agent.translator import ClaudeAgentTranslator

__version__ = "0.1.0"

__all__ = ["ClaudeAgentTranslator", "__version__"]
