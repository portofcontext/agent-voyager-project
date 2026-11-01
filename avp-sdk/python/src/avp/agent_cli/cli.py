"""The command line."""

import asyncio
import signal
import sys
from collections.abc import Awaitable
from pathlib import Path
from typing import Annotated

import typer

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
    app = typer.Typer(
        help="An AVP agent. Not part of the AVP spec.",
        add_completion=False,
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )
    out_option = typer.Option(help="Where to write it (default: stdout).")

    @app.command("ping")
    def ping_command(out: Annotated[Path | None, out_option] = None) -> None:
        """Write {"type": "pong"} without loading the agent, to check it runs."""
        _write(out, '{"type": "pong"}\n')

    @app.command("describe")
    def describe_command(out: Annotated[Path | None, out_option] = None) -> None:
        """Write the agent's Descriptor."""
        descriptor = asyncio.run(get_descriptor(describe))
        _write(out, descriptor.model_dump_json(exclude_none=True, indent=2) + "\n")

    @app.command("run")
    def run_command(
        commission: Annotated[str, typer.Option(help="A path, or inline JSON.")],
        out: Annotated[str, typer.Option(help="Where to write the NDJSON, or -.")],
    ) -> None:
        """Run a Commission."""
        sink = ndjson_sink(None if out == "-" else Path(out))
        try:
            asyncio.run(_interruptible(run(read_commission(commission), sink)))
        except asyncio.CancelledError:
            raise typer.Exit(130) from None

    try:
        app(args=argv, prog_name=prog)
    except SystemExit as ended:
        return ended.code if isinstance(ended.code, int) else 0
    return 0
