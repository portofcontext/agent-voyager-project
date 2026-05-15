# AVP Claude Agent SDK

Goals:
* Make the claude-agent-sdk AVP compliant (../../spec/v0.1)
* Wrap `ClaudeSDKClient` (not `query()`) as the primary AVP surface. `query()` is out of scope for v0.1: it has no pre-run lifecycle hook, so an accurate `AgentDescriptor` (tool list via `get_mcp_status()`) and a conformant `agent_started` event are impossible without a `connect()` phase.
* Expose `AVPClaudeSDKClient` as a drop-in subclass/wrapper of `ClaudeSDKClient` that emits a full AVP trajectory: `agent_started` (with real tool list) → model/tool events → `agent_stopped`.
* Expose an entry point for an AVP supervisor to trigger the agent with a Commission.

## Patching approach

`ClaudeSDKClient` is wrapped, not monkeypatched at the module level:

* `AVPClaudeSDKClient` subclasses (or delegates to) `ClaudeSDKClient`.
* `connect()` is overridden: calls `super().connect()`, then `get_mcp_status()` to build the `AgentDescriptor`, then emits `agent_started`.
* `query()` is overridden: tees the message stream through AVP event emission before yielding each message.
* `disconnect()` is overridden: emits `agent_stopped`, then calls `super().disconnect()`.
* A `setup_avp()` monkeypatch remains available for users who cannot change their import, but it replaces `claude_agent_sdk.ClaudeSDKClient` with `AVPClaudeSDKClient`, not `query()`.

## Code best practices
* always use `uv` CLI when adding / updating dependencies
* avoid using `Any` or `dict[str, Any]` typing when possible
* Include compact, non-verbose docstrings

## Documentation

As the project is being scoped, implemented, and iterated on keep documentation in the form of `.md` files in the
`./docs` directory.

Requirements:
* Keep documentation tight and compact, excessive docs will slow down humans and make it harder to onboard.
* Prefer bullet points and diagrams to long scentences / paragraphs
* Consult the existing files / directory structure within `docs/` to determine what documentation needs to be read, written, or updated to avoid repetition and assumtions on the current state of the project.
