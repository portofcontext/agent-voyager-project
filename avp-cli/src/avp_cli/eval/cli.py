"""`avp eval`: run eval files, and look at past eval runs."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from avp_cli import console, paths
from avp_cli.console import Failed, VerboseOption, err, line, out
from avp_cli.eval import results
from avp_cli.eval.commission import EvalError, load
from avp_cli.eval.config import EvalConfig
from avp_cli.eval.engine import run_eval
from avp_cli.eval.report import print_scoreboard
from avp_cli.eval.results import RunResult
from avp_cli.eval.scoring import Result
from avp_cli.runs import environment, volumes
from avp_cli.runs.dispatch import Options

app = typer.Typer(
    no_args_is_help=True,
    help="Run datasets against agents and Commissions, and score the results.",
)

JsonOption = Annotated[bool, typer.Option("--json", help="Print JSON.")]


@app.command("run")
def run(
    path: Annotated[Path, typer.Argument(help="The eval file.")],
    agent: Annotated[
        list[str] | None, typer.Option(help="Run these agents instead of the file's.")
    ] = None,
    concurrency: Annotated[int, typer.Option(min=1, help="How many runs at once.")] = 1,
    env: Annotated[
        list[str] | None,
        typer.Option(
            help="NAME=VALUE for every agent's environment, or NAME to copy it from yours."
        ),
    ] = None,
    env_file: Annotated[
        list[Path] | None,
        typer.Option(help="A file of NAME=VALUE lines for every agent's environment."),
    ] = None,
    allow_host: Annotated[
        list[str] | None,
        typer.Option(help="Another host every agent may reach, as `avp run` takes it."),
    ] = None,
    volume: Annotated[
        list[str] | None,
        typer.Option(
            "--volume", "-v", help="HOST:SANDBOX[:ro] to mount a host path in every sandbox."
        ),
    ] = None,
    model: Annotated[str | None, typer.Option(help="Use this model for every Commission.")] = None,
    max_items: Annotated[
        int | None, typer.Option(min=1, help="Run only the first this many items.")
    ] = None,
    threshold: Annotated[
        float | None, typer.Option(min=0, max=1, help="Exit 1 when accuracy is below this.")
    ] = None,
    resume: Annotated[str | None, typer.Option(help="Finish this earlier eval run.")] = None,
    json: JsonOption = False,
    verbose: VerboseOption = False,
) -> None:
    """Run an eval file and print the scoreboard. Every Commission runs on every
    agent for every item, each in its own sandbox, as `avp run` runs it. The
    eval's runs and results are kept in ~/.avp/evals/."""
    console.set_verbose(verbose)
    for flag, value in [("--model", model), ("--resume", resume)]:
        if value is not None:
            raise Failed(f"{flag} isn't built yet")
    try:
        ev = load(path)
    except EvalError as error:
        raise Failed(str(error)) from None
    if max_items is not None:
        ev = ev.model_copy(update={"dataset": ev.dataset[:max_items]})
    try:
        config = EvalConfig.from_eval(ev, path.parent, agent)
    except EvalError as error:
        raise Failed(_problems(path, error)) from None
    options = Options(
        env=environment.variables(env or [], env_file or []),
        allow_hosts=allow_host or [],
        volumes=volumes.parse(volume or []),
    )
    for case in config:
        environment.check(case.built, options.env)
    total = len(config.commissions) * len(config.agents) * len(config.dataset)
    directory, saved = results.create(ev.name, path.read_text())
    console.detail(f"Eval directory: {directory}")

    with err.status(line("Running ", (ev.name, "bold"), f" - 0 of {total}")) as status:

        def progress(result: Result) -> None:
            saved.runs.append(RunResult.of(result, directory))
            results.save(directory, saved)
            status.update(line("Running ", (ev.name, "bold"), f" - {len(saved.runs)} of {total}"))

        try:
            found = asyncio.run(run_eval(config, directory, options, concurrency, progress))
        except KeyboardInterrupt:
            found = None
    if found is None:
        err.print(
            f"Stopped after {len(saved.runs)} of {total} runs; their results are in"
            f" {directory / results.RESULTS}",
            highlight=False,
            soft_wrap=True,
        )
        raise typer.Exit(130)
    saved.runs = [RunResult.of(r, directory) for r in found]
    saved.finished = datetime.now(UTC)
    results.save(directory, saved)
    if json:
        out.print_json(saved.model_dump_json())
    else:
        print_scoreboard(out, saved, directory)
        out.print(f"\nResults: {directory / results.RESULTS}", highlight=False, soft_wrap=True)
    accuracy = saved.summary().accuracy
    if threshold is not None and (accuracy is None or accuracy < threshold):
        raise typer.Exit(1)


def _problems(path: Path, error: EvalError) -> str:
    """The problems as a list. The engine doesn't know about --agent, so the
    hint is added here."""
    found = [f"{p}; give --agent" if p.startswith("no agents:") else p for p in error.problems]
    return f"{path} can't run:\n" + "\n".join(f"  {p}" for p in found)


@app.command("list")
def list_evals(limit: Annotated[int, typer.Option(help="Show this many runs.")] = 20) -> None:
    """List past eval runs, the latest first."""
    root = paths.evals()
    ids = sorted((p.name for p in root.iterdir()), reverse=True)[:limit] if root.is_dir() else []
    table = Table("ID", "Started", "Runs", "Accuracy", "Pass rate")
    for id in ids:
        try:
            _, saved = results.load(id)
        except Failed:
            continue
        summary = saved.summary()
        table.add_row(
            id,
            f"{saved.started:%Y-%m-%d %H:%M}" + ("" if saved.finished else " (stopped)"),
            str(summary.runs),
            "-" if summary.accuracy is None else f"{summary.accuracy:.0%}",
            "-" if summary.pass_rate is None else f"{summary.pass_rate:.0%}",
        )
    out.print(table)


@app.command("show")
def show(
    id: Annotated[str | None, typer.Argument(help="The eval run; the latest when omitted.")] = None,
    agent: Annotated[str | None, typer.Option(help="Show only this agent.")] = None,
    json: JsonOption = False,
) -> None:
    """Print a past eval's scoreboard and the runs that didn't pass, as `eval
    run` prints them at the end."""
    directory, saved = results.load(id)
    if agent is not None:
        saved = saved.model_copy(update={"runs": [r for r in saved.runs if r.agent == agent]})
    if json:
        out.print_json(saved.model_dump_json())
    else:
        print_scoreboard(out, saved, directory)


@app.command("delete")
def delete(
    id: Annotated[str | None, typer.Argument(help="The eval run to delete.")] = None,
    all: Annotated[bool, typer.Option("--all", help="Delete every eval run.")] = False,
) -> None:
    """Delete past eval runs and their runs' directories."""
    raise NotImplementedError
