"""AVP instrumentation for `claude_agent_sdk`.

Primary surface: `AVPClaudeSDKClient`, a subclass of
`claude_agent_sdk.ClaudeSDKClient` that emits a conforming AVP
trajectory across `connect()` / `receive_response()` / `disconnect()`.

`setup_avp(sink=...)` is the module-level monkeypatch alternative: it
swaps `claude_agent_sdk.ClaudeSDKClient` for the AVP wrapper so callers
who can't change their import still get instrumentation.

Stage 3 will add `run_avp_agent` (Commission-driven entry point).
"""

from avp_claude_agent_sdk._client import AVPClaudeSDKClient
from avp_claude_agent_sdk._patches import setup_avp
from avp_claude_agent_sdk._run_agent import run_avp_agent

__all__ = ["AVPClaudeSDKClient", "run_avp_agent", "setup_avp"]
