"""AVP-compliant facade over `claude_agent_sdk`.

Swap `from claude_agent_sdk import query` for
`from avp_claude_agent_sdk import query` to get AVP trajectory emission
with the same call surface. Use `run_avp_agent` for the monkeypatch path.
"""

from avp_claude_agent_sdk._agent import run_avp_agent
from avp_claude_agent_sdk.query import query

__all__ = ["query", "run_avp_agent"]
