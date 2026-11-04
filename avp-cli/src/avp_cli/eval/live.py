"""Running an eval from a command: the engine under a spinner that counts runs,
and Ctrl-C."""

import asyncio
from collections.abc import Callable
from pathlib import Path

import typer
from rich.text import Text

from avp_cli.console import err, line
from avp_cli.eval.config import EvalConfig
from avp_cli.eval.engine import run_eval
from avp_cli.eval.scoring import Result
from avp_cli.runs.dispatch import Options


def run_live(
    config: EvalConfig,
    directory: Path,
    options: Options,
    concurrency: int,
    kept: Path,
    on_result: Callable[[Result], None] = lambda _: None,
) -> list[Result]:
    """`run_eval`, showing how many runs have finished. `on_result` is called
    as each run is scored. On Ctrl-C, says how many finished, that they are in
    `kept`, and exits 130."""
    total = len(config.commissions) * len(config.agents) * len(config.dataset)
    done = 0

    def running() -> Text:
        return line("Running ", (config.name, "bold"), f" - {done} of {total}")

    with err.status(running()) as status:

        def progress(result: Result) -> None:
            nonlocal done
            done += 1
            on_result(result)
            status.update(running())

        try:
            return asyncio.run(run_eval(config, directory, options, concurrency, progress))
        except KeyboardInterrupt:
            pass
    err.print(
        f"Stopped after {done} of {total} runs; their results are in {kept}",
        highlight=False,
        soft_wrap=True,
    )
    raise typer.Exit(130)
