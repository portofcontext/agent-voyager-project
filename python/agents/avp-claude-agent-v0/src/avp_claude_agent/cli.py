"""`avp-claude-agent` stdio entry point.

Reads ONE Commission JSON from stdin, runs a ClaudeAgentTranslator, streams NDJSON
events to stdout.

Note: until the SDK integration TODOs in translator.py are filled in, this
CLI errors out with NotImplementedError on its first SDK call. The CLI shape
is durable; the SDK glue is the part that needs to be wired against the
specific claude_agent_sdk version you ship with.
"""

from __future__ import annotations

import argparse
import json
import sys

from avp.commission import Commission
from avp.io import write_event
from avp_claude_agent.descriptor import descriptor as build_descriptor
from avp_claude_agent.translator import ClaudeAgentTranslator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avp-claude-agent-sdk",
        description=(
            "AVP v0.1 agent for the Claude Agent SDK (observer pattern). "
            "Reads a Commission from stdin, streams events to stdout."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser(
        "describe",
        help=(
            "Print this agent's Descriptor as JSON to stdout and exit. The "
            "payload matches the `agent_described` event the agent emits "
            "between `run_requested` and `agent_started` for the same "
            "agent build."
        ),
    )
    args = parser.parse_args(argv)

    if args.subcommand == "describe":
        sys.stdout.write(
            json.dumps(
                build_descriptor().model_dump(by_alias=True, exclude_none=True),
                indent=2,
            )
            + "\n"
        )
        return 0

    commission_blob = sys.stdin.readline()
    if not commission_blob.strip():
        print("avp-claude-agent: expected one Commission JSON line on stdin", file=sys.stderr)
        return 2
    commission = Commission.model_validate(json.loads(commission_blob))

    translator = ClaudeAgentTranslator(
        commission=commission,
        on_event=lambda ev: write_event(ev, file=sys.stdout),
        descriptor=build_descriptor(),
    )
    translator.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
