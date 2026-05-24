"""Conformance entrypoint for avp-claude-agent-sdk.

Exposes the agent CLI contract consumed by `avp-conformance`:

- `ping --out <path>` — write a single `{"type": "pong"}` line and exit.
- `run --commission <json|path> [--built-in <json|path>] --out <path>` —
  run the agent against the given Commission and emit AVP trajectory
  events to the output file. Currently a stub that validates inputs and
  writes one self-describing line; real dispatch lands later.

See the avp package's `conformance/CHECKLIST.md` for the SDK-author flow.
Argparse is intentional here: this entrypoint stays stdlib-only so it
doesn't pull a CLI framework into the agent package.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from avp.conformance.utils import load_built_in, load_commission


def _cmd_ping(args: argparse.Namespace) -> int:
    Path(args.out).write_text(json.dumps({"type": "pong"}) + "\n")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Stub: validate inputs, write one self-describing line to --out.

    Real agent dispatch is not yet wired. This exists so the conformance
    CLI's dispatch side can be exercised end-to-end before the Claude Agent
    SDK is plugged in.
    """
    commission = load_commission(args.commission)
    built_in = load_built_in(args.built_in) if args.built_in is not None else None
    stub_event = {
        "type": "stub",
        "data": {
            "commission_run_id": commission.run_id,
            "built_in_present": built_in is not None,
            "note": "real agent dispatch not yet implemented",
        },
    }
    Path(args.out).write_text(json.dumps(stub_event) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avp-claude-agent-sdk-conformance",
        description="Conformance entrypoint for avp-claude-agent-sdk.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ping = sub.add_parser("ping", help='Write {"type": "pong"} to --out and exit.')
    p_ping.add_argument("--out", required=True)
    p_ping.set_defaults(func=_cmd_ping)

    p_run = sub.add_parser("run", help="Run the agent against a Commission (currently a stub).")
    p_run.add_argument("--commission", required=True)
    p_run.add_argument("--built-in", dest="built_in", required=False)
    p_run.add_argument("--out", required=True)
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
