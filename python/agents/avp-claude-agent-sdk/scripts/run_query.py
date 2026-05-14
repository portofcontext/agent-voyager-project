"""Smoke-test script: run `claude_agent_sdk.query` with AVP patches applied.

Usage:
    uv --directory python run python agents/avp-claude-agent-sdk/scripts/run_query.py "your prompt"
    uv --directory python run python agents/avp-claude-agent-sdk/scripts/run_query.py --model claude-haiku-4-5-20251001 "ping"

`apply_patches()` replaces `claude_agent_sdk.query` with the AVP-emitting
wrapper before the first call. The trajectory NDJSON goes to stdout via
the default `stdio_sink`; SDK messages are dumped to stderr so stdout
stays pipe-friendly (`... | jq` etc.).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys

from claude_agent_sdk import query
from claude_agent_sdk.types import ClaudeAgentOptions

from avp_claude_agent_sdk import setup_avp

setup_avp()


async def _run(prompt: str, model: str | None) -> None:
    options = ClaudeAgentOptions(model=model) if model else ClaudeAgentOptions()
    async for message in query(prompt=prompt, options=options):
        payload = dataclasses.asdict(message) if dataclasses.is_dataclass(message) else message
        print(json.dumps(payload, default=str), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_query",
        description="Run claude_agent_sdk.query with AVP patches; trajectory NDJSON → stdout, messages → stderr.",
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
