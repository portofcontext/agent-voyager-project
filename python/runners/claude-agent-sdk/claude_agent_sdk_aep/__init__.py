"""claude-agent-sdk-aep — AEP runner for the Claude Agent SDK.

Wraps ``claude_agent_sdk.query`` so every run automatically emits an AEP
event stream (NDJSON to stdout). Works in two modes:

**Library mode** — drop-in replacement for ``claude_agent_sdk.query``::

    from claude_agent_sdk_aep import query
    from claude_agent_sdk import ClaudeAgentOptions

    async for message in query(
        prompt="Find and fix the bug in auth.py",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"]),
    ):
        ...

**Subprocess / runner mode** — launched by a supervisor that writes AEP
config JSON to the runner's stdin::

    from claude_agent_sdk_aep import run_from_stdin
    run_from_stdin()           # reads config, writes stream, handles hooks

    # or via CLI:
    #   claude-aep-runner
    #   python -m claude_agent_sdk_aep
"""

from ._query import query, aep_options
from ._run import run_from_stdin
from ._supervisor import supervise

__all__ = ["query", "aep_options", "run_from_stdin", "supervise"]
