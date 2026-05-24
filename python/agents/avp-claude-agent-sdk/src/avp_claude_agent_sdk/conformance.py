"""Conformance entrypoint for avp-claude-agent-sdk.

Exposes the agent CLI contract consumed by `avp-conformance`:

- `ping --out <path>` — write a single `{"type": "pong"}` line and exit.
- `run --commission <json|path> [--built-in <json|path>] --out <path>` —
  run the agent against the given Commission and emit AVP trajectory
  events to the output file. (Not yet implemented.)

See `conformance/AGENT-CLI.md` in the avp package for the contract details.
Argparse is intentional here: this entrypoint stays stdlib-only so it
doesn't pull a CLI framework into the agent package.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cmd_ping(args: argparse.Namespace) -> int:
    Path(args.out).write_text(json.dumps({"type": "pong"}) + "\n")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    print("error: `run` is not implemented yet", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avp-claude-agent-sdk-conformance",
        description="Conformance entrypoint for avp-claude-agent-sdk.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ping = sub.add_parser("ping", help='Write {"type": "pong"} to --out and exit.')
    p_ping.add_argument("--out", required=True)
    p_ping.set_defaults(func=_cmd_ping)

    p_run = sub.add_parser("run", help="Run the agent with a Commission (not yet implemented).")
    p_run.add_argument("--commission", required=True)
    p_run.add_argument("--built-in", dest="built_in", required=False)
    p_run.add_argument("--out", required=True)
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
