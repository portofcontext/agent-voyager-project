# AVP Claude Agent SDK

Goals:
* Make the claude-agent-sdk AVP compliant
* Allow users to simply change the imports from `claude_agent_sdk` to `avp_claude_agent_sdk` when they are using the 2 primary exports: `query()` and `ClaudeSDKClient` and recieve AVP trajectories out of the box. An alternative is also creating a monkeypatch function like Braintrust `setup_claude_agent_sdk`.
* expose an entry point for a AVP supervisor to trigger the agent with a Commision.

## Code best practices
* always use `uv` CLI when adding / updating dependencies
* avoid using `Any` or `dict[str, Any]` typing when possible
* Include compact, non-verbose docstrings
