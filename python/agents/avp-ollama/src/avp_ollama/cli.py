"""`avp-ollama run <run_id>` — drive a single run synchronously without
the FastAPI dispatch layer. Useful for manual testing and local debugging.

The supervisor must already have the Run row created; this just fetches
the config and runs the translator inline."""

from __future__ import annotations

import argparse
import logging
import sys

from .runner import _drive_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="avp-ollama")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Drive a run from a pre-created Run row.")
    p_run.add_argument("run_id", help="The supervisor's run_id.")
    p_run.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging."
    )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.cmd == "run":
        _drive_run(args.run_id)
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
