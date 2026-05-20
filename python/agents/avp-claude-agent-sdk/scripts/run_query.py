"""Smoke-test script: run a prompt through a `setup_avp()`-instrumented
`claude_agent_sdk.ClaudeSDKClient`.

Usage:
    uv --directory python run python agents/avp-claude-agent-sdk/scripts/run_query.py "your prompt"
    uv --directory python run python agents/avp-claude-agent-sdk/scripts/run_query.py --model claude-haiku-4-5-20251001 "ping"

The script imports `ClaudeSDKClient` from `claude_agent_sdk` as a plain
user would; `setup_avp(sink=...)` is called before the first instance
is constructed so the module-level monkeypatch rebinds the import to
the AVP wrapper. SDK messages and AVP events stream to separate rich
log files under `scripts/logs/`.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import ClaudeAgentOptions
from rich.console import Console

from avp.trajectory import Event
from avp_claude_agent_sdk import setup_avp

SCRIPTS_DIR = Path(__file__).resolve().parent


async def _run(prompt: str, model: str | None) -> None:
    options = ClaudeAgentOptions(model=model, permission_mode="auto")

    with (
        (SCRIPTS_DIR / "logs/claude.log").open("w") as claude_file,
        (SCRIPTS_DIR / "logs/avp.log").open("w") as avp_file,
    ):
        claude_console = Console(file=claude_file, no_color=True, markup=False)
        avp_console = Console(file=avp_file, no_color=True, markup=False)

        counter = 0

        async def rich_sink(e: Event):
            nonlocal counter
            counter += 1
            avp_console.print("\n" + "*" * 40 + f" [{counter}] AVP ({e.type}) " + "*" * 40)
            avp_console.print(e)

        setup_avp(sink=rich_sink)
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                counter += 1
                claude_console.print(
                    "\n" + "=" * 40 + f" [{counter}] CLAUDE ({type(message).__name__})" + "=" * 40
                )
                claude_console.print(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_query",
        description=(
            "Drive AVPClaudeSDKClient with a single prompt; trajectory NDJSON → .jsonl file, "
            "SDK messages → stderr."
        ),
    )
    parser.add_argument("prompt", help="Prompt to send to the agent.")
    parser.add_argument(
        "--model", default=None, help="Override the model (e.g. claude-haiku-4-5-20251001)."
    )
    args = parser.parse_args(argv)

    asyncio.run(_run(args.prompt, args.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
