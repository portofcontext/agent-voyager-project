"""`avp-openai-agent` stdio entry point.

Reads ONE Commission JSON from stdin, runs an OpenAIAgentTranslator,
streams NDJSON events to stdout.

`avp-openai-agent describe` prints the AgentDescriptor and exits — same
payload the translator emits in the `agent_described` event between
`run_requested` and `agent_started`.
"""

from __future__ import annotations

import argparse
import json
import sys

from avp import Commission, write_event
from avp_openai_agent.descriptor import descriptor as build_descriptor
from avp_openai_agent.translator import OpenAIAgentTranslator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avp-openai-agent",
        description=(
            "AVP v0.1 agent for the OpenAI Agents SDK (observer pattern). "
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
        print(
            "avp-openai-agent: expected one Commission JSON line on stdin",
            file=sys.stderr,
        )
        return 2
    commission = Commission.model_validate(json.loads(commission_blob))

    translator = OpenAIAgentTranslator(
        commission=commission,
        on_event=lambda ev: write_event(ev, file=sys.stdout),
        descriptor=build_descriptor(),
    )
    translator.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
