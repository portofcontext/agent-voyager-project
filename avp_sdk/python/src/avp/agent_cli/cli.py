"""The command line."""

import argparse
import asyncio
import signal
import sys
from collections.abc import Awaitable
from pathlib import Path

from avp.agent_cli.run import DescribeFn, RunFn, get_descriptor, read_commission
from avp.agent_cli.sink import ndjson_sink


async def _interruptible(task: Awaitable[None]) -> None:
    """Await `task` with SIGINT and SIGTERM cancelling it."""
    future = asyncio.ensure_future(task)
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for sig in signals:
        loop.add_signal_handler(sig, future.cancel)
    try:
        await future
    finally:
        for sig in signals:
            loop.remove_signal_handler(sig)


def _write(out: Path | None, text: str) -> None:
    if out is None:
        sys.stdout.write(text)
    else:
        out.write_text(text)


def main(
    *, run: RunFn, describe: DescribeFn, prog: str | None = None, argv: list[str] | None = None
) -> int:
    """Run the command and return its exit code: 0 when the Trajectory is
    complete (a refusal included), 130 when SIGINT or SIGTERM cancelled `run`.
    `ping` never calls `run` or `describe`, so keep heavy imports inside them."""
    parser = argparse.ArgumentParser(
        prog=prog, description="An AVP agent. Not part of the AVP spec."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    ping_parser = commands.add_parser(
        "ping", help='Write {"type": "pong"} without loading the agent, to check it runs.'
    )
    ping_parser.add_argument("--out", type=Path, help="Where to write it (default: stdout).")
    describe_parser = commands.add_parser("describe", help="Write the agent's Descriptor.")
    describe_parser.add_argument("--out", type=Path, help="Where to write it (default: stdout).")
    run_parser = commands.add_parser("run", help="Run a Commission.")
    run_parser.add_argument("--commission", required=True, help="A path, or inline JSON.")
    run_parser.add_argument("--out", required=True, help="Where to write the NDJSON, or -.")
    args = parser.parse_args(argv)

    if args.command == "ping":
        _write(args.out, '{"type": "pong"}\n')
        return 0

    if args.command == "describe":
        descriptor = asyncio.run(get_descriptor(describe))
        _write(args.out, descriptor.model_dump_json(exclude_none=True, indent=2) + "\n")
        return 0

    sink = ndjson_sink(None if args.out == "-" else Path(args.out))
    try:
        received = read_commission(args.commission)
        asyncio.run(_interruptible(run(received, sink)))
    except asyncio.CancelledError:
        return 130
    return 0
