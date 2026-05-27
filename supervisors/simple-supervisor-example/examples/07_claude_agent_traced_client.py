"""Example 07 — AVP-instrumented Claude Agent SDK loop.

Companion to example 06 (which does the same for the raw Anthropic
Messages SDK). The Claude Agent SDK runs tools internally via its hook
protocol; user code just iterates `receive_response()`.

The change to add AVP: use `AVPClaudeSDKClient` (a drop-in subclass of
`ClaudeSDKClient`) and give it a `sink`. It emits the conforming
trajectory across `query()` / `receive_response()` / `disconnect()`;
your existing message-handling body is unchanged.

Run:
  ANTHROPIC_API_KEY=... python examples/07_claude_agent_traced_client.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from avp.commission import Commission
from avp.trajectory import event_to_wire


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2
    if importlib.util.find_spec("claude_agent_sdk") is None:
        print("error: install claude-agent-sdk (pip install claude-agent-sdk)", file=sys.stderr)
        return 2
    if shutil.which("claude") is None:
        print("error: install the Claude Code CLI; `claude` must be on PATH", file=sys.stderr)
        return 2

    from avp_claude_agent_sdk import AVPClaudeSDKClient

    workspace = Path(tempfile.mkdtemp(prefix="avp-traced-claude-"))
    target = workspace / "hello.py"

    commission = Commission(
        schema_version="0.1",
        run_id=f"traced-claude-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
        model="claude-haiku-4-5-20251001",
        prompt=(
            f"Create the file {target} containing a Python function "
            "`greet(name)` that returns 'hello, ' plus the name. Include "
            "a one-line docstring. Then say DONE."
        ),
    )

    async def _print_sink(event) -> None:
        # Machine-readable NDJSON; swap for a pretty renderer if you like.
        print(json.dumps(event_to_wire(event)))

    # Compare to a plain ClaudeSDKClient loop:
    #
    #     async with ClaudeSDKClient(options=opts) as client:
    #         await client.query(prompt)
    #         async for message in client.receive_response():
    #             handle(message)
    #
    # The only change: `AVPClaudeSDKClient(commission=..., sink=...)` in place
    # of `ClaudeSDKClient(options=...)`. AVP events for each message are on the
    # wire by the time your handler sees it.
    async def _run() -> None:
        async with AVPClaudeSDKClient(commission=commission, sink=_print_sink) as client:
            await client.query(commission.prompt)
            async for _message in client.receive_response():
                # Your existing message-handling goes here.
                pass

    # Workdir is the tempdir so the SDK's Write tool lands inside it.
    cwd = os.getcwd()
    try:
        os.chdir(workspace)
        asyncio.run(_run())
    finally:
        os.chdir(cwd)

    print(f"\nworkspace: {workspace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
