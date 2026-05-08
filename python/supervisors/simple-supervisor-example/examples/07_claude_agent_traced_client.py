"""Example 07 — drop-in instrumentation for an existing Claude Agent SDK loop.

Companion to example 06 (which does the same thing for the Anthropic
Messages SDK). The Claude Agent SDK runs tools internally via its hook
protocol; user code just iterates `receive_response()`.

The change to add AVP: wrap the loop in `with AVPTracer(...)` and use
`traced_claude_sdk_client()` (no args) instead of `ClaudeSDKClient(options=)`.
The factory pulls Commission from the active tracer; the SDK's hooks emit
AVP events as turns and tools fire.

Run:
  ANTHROPIC_API_KEY=... python examples/07_claude_agent_traced_client.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from avp import AVPTracer, Commission, print_event
from avp_claude_agent import traced_claude_sdk_client


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
        exposed=["Write", "Read", "Bash"],
    )

    # Compare to a plain ClaudeSDKClient loop:
    #
    #     async with ClaudeSDKClient(options=opts) as client:
    #         await client.connect(prompt)
    #         async for message in client.receive_response():
    #             handle(message)
    #
    # Two changes:
    #   - wrap with `AVPTracer(commission, on_event=...)` (sets the active tracer)
    #   - `traced_claude_sdk_client()` replaces `ClaudeSDKClient(options=)`;
    #     Commission flows from the active tracer
    async def _run() -> None:
        with AVPTracer(commission, on_event=print_event):
            async with traced_claude_sdk_client() as client:
                await client.connect(commission.prompt)
                async for _message in client.receive_response():
                    # Your existing message-handling goes here. AVP events for
                    # this message are already on the wire by the time we get
                    # here. The user's body could render to a UI, route the
                    # message, log it, etc.
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
