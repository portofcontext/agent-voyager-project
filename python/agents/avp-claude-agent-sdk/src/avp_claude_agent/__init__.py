"""AVP-compliant facade over `claude_agent_sdk`.

Swap `from claude_agent_sdk import query` for
`from avp_claude_agent import query` to get AVP trajectory emission with
the same call surface.
"""

from .query import query

__all__ = ["query"]
