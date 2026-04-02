"""anthropic-aep — AEP runner for the Anthropic Python SDK.

Wraps the Anthropic Python SDK so every run automatically emits an AEP
event stream (NDJSON to stdout). Works in two modes:

**Library mode** — bring your own tools, one import change::

    from anthropic_aep import query

    tools = [
        {
            "name": "search",
            "description": "Search the web",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
    ]

    async for message in query(
        prompt="Search for recent Python news",
        tools=tools,
        tool_handlers={"search": lambda inp: f"Results for: {inp['query']}"},
    ):
        ...

**Subprocess / runner mode** — launched by a supervisor that writes AEP
config JSON to the runner's stdin::

    from anthropic_aep import run_from_stdin
    run_from_stdin()           # reads config, writes stream

    # or via CLI:
    #   anthropic-aep-runner
    #   python -m anthropic_aep
"""

from ._query import query
from ._run import run_from_stdin
from ._supervisor import supervise

__all__ = ["query", "run_from_stdin", "supervise"]
