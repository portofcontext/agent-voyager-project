"""Entry point for ``python -m claude_agent_sdk_aep``.

Reads AEP config JSON from stdin and runs the agent, emitting the AEP
event stream to stdout.

Usage::

    echo '{"run_id":"r1","prompt":"say hello","model":"anthropic/claude-haiku-4-5-20251001"}' \\
        | python -m claude_agent_sdk_aep
"""

from ._run import run_from_stdin

run_from_stdin()
