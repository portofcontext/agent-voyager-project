"""Smoke-test script: run a prompt through `AVPClaudeSDKClient`.

Usage:
    uv --directory python run python agents/avp-claude-agent-sdk/scripts/run_query.py "your prompt"
    uv --directory python run python agents/avp-claude-agent-sdk/scripts/run_query.py --model claude-haiku-4-5-20251001 "ping"
    uv --directory python run python agents/avp-claude-agent-sdk/scripts/run_query.py --out run.jsonl "your prompt"

Trajectory NDJSON is written to a `.jsonl` file (default
`trajectory.jsonl`) via a file-backed sink; SDK messages are dumped to
stderr so stdout stays clean.
"""

from __future__ import annotations

import argparse
import asyncio

from claude_agent_sdk.types import ClaudeAgentOptions
from rich import print

from avp.trajectory import Event
from avp_claude_agent_sdk import AVPClaudeSDKClient


async def _run(prompt: str, model: str | None) -> None:
    options = ClaudeAgentOptions(model=model) if model else ClaudeAgentOptions()

    async def rich_sink(e: Event):
        print("*" * 40 + "AVP Event" + "*" * 40)
        print(e)

    async with AVPClaudeSDKClient(options=options, sink=rich_sink) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            print("=" * 40 + "Claude Message" + "=" * 40)
            print(message)


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
