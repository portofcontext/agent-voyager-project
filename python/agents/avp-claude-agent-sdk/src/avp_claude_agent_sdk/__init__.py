"""AVP instrumentation for `claude_agent_sdk`.

Call `setup_avp()` once (with an optional `sink`) to instrument
`claude_agent_sdk.query` in place. All subsequent calls to
`claude_agent_sdk.query` emit a conforming AVP trajectory.
"""

from avp_claude_agent_sdk._agent import run_avp_agent
from avp_claude_agent_sdk._patches import setup_avp

__all__ = ["run_avp_agent", "setup_avp"]
