"""`aep-claude-agent` stdio entry point.

Reads ONE Config JSON from stdin, runs a ClaudeAgentTranslator, streams NDJSON
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

from aep import Config, write_event
from aep_claude_agent.translator import ClaudeAgentTranslator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aep-claude-agent",
        description=(
            "AEP v0.1 runner for the Claude Agent SDK (observer pattern). "
            "Reads a Config from stdin, streams events to stdout."
        ),
    )
    parser.parse_args(argv)

    config_blob = sys.stdin.readline()
    if not config_blob.strip():
        print("aep-claude-agent: expected one Config JSON line on stdin", file=sys.stderr)
        return 2
    config = Config.model_validate(json.loads(config_blob))

    translator = ClaudeAgentTranslator(
        config=config,
        on_event=lambda ev: write_event(ev, file=sys.stdout),
    )
    translator.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
