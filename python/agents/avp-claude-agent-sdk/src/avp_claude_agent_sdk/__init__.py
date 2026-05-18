"""AVP instrumentation for `claude_agent_sdk`.

Primary surface: `AVPClaudeSDKClient`, a subclass of
`claude_agent_sdk.ClaudeSDKClient` that emits a conforming AVP
trajectory across `connect()` / `receive_response()` / `disconnect()`.

Stage 3 will add `run_avp_agent` (Commission-driven entry point) and
`setup_avp` (module-level monkeypatch that swaps `ClaudeSDKClient` for
`AVPClaudeSDKClient`).
"""

from avp_claude_agent_sdk._client import AVPClaudeSDKClient

__all__ = ["AVPClaudeSDKClient"]
