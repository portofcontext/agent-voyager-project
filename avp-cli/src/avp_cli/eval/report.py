"""The scoreboard `eval run` prints at the end and `eval show` prints for a
past eval."""

from pathlib import Path

from rich.console import Console, Group, RenderableType
from rich.table import Table
from rich.text import Text

from avp_cli.eval.results import EvalResults, RunResult


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def scoreboard(results: EvalResults, directory: Path) -> RenderableType:
    """One row per Commission and agent, then the runs that didn't pass."""
    runs = results.runs
    board = Table("Commission", "Agent", "Runs", "Accuracy", "Pass rate", "Scorer failed")
    pairs = dict.fromkeys((r.commission, r.agent) for r in runs)
    for commission, name in pairs:
        summary = results.summary(commission, name)
        board.add_row(
            commission,
            name,
            str(summary.runs),
            _percent(summary.accuracy),
            _percent(summary.pass_rate),
            str(summary.scorer_failures) if summary.scorer_failures else "-",
        )
    parts: list[RenderableType] = [Text(f"{results.name} ({results.id})", style="bold"), board]
    failed = [r for r in runs if r.score is None or not r.score.passed]
    if failed:
        table = Table("Item", "Commission", "Agent", "Why", "Run")
        for r in failed:
            table.add_row(r.item, r.commission, r.agent, _why(r), str(directory / r.directory))
        parts += [Text("Runs that didn't pass", style="bold"), table]
    if results.finished is None:
        parts.append(Text("The eval stopped before every run finished.", style="yellow"))
    return Group(*parts)


def _why(run: RunResult) -> Text:
    if run.score is None:
        return Text(f"scorer failed: {run.scorer_error}", style="red")
    return Text("\n".join(run.score.reasons) or "failed")


def print_scoreboard(console: Console, results: EvalResults, directory: Path) -> None:
    console.print(scoreboard(results, directory))
