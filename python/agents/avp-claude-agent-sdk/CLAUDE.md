# AVP Claude Agent SDK

Goals:
* Make the claude-agent-sdk AVP compliant (../../spec/v0.1)
* Allow users to simply change the imports from `claude_agent_sdk` to `avp_claude_agent_sdk` when they are using the 2 primary exports: `query()` and `ClaudeSDKClient` and recieve AVP trajectories out of the box. An alternative is also creating a monkeypatch function like Braintrust `setup_claude_agent_sdk`.
* expose an entry point for a AVP supervisor to trigger the agent with a Commision.

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
