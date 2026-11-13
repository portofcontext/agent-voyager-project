"""The scoreboard `eval run` prints at the end and `eval show` prints for a
past eval."""

from pathlib import Path

from rich.console import Console, Group, RenderableType
from rich.table import Table
from rich.text import Text

from avp_cli.eval.results import EvalResults, RunResult, agents


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _money(value: float | None) -> str:
    return "-" if value is None else f"${value:.4f}"


def _seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}s"


def scoreboard(results: EvalResults, directory: Path) -> RenderableType:
    """The agents, one row per Commission and agent, then the runs that
    didn't pass. Cost, turns, and time are per run, over the runs that
    started."""
    runs = results.runs
    board = Table(
        "Commission",
        "Agent",
        "Model",
        "Runs",
        "Accuracy",
        "Pass rate",
        "$/run",
        "Turns/run",
        "Time/run",
        "Scorer failed",
    )
    pairs = dict.fromkeys((r.commission, r.agent) for r in runs)
    for commission, name in pairs:
        rows = results.of(commission, name)
        started = [r for r in rows if r.seconds is not None]
        summary = results.summary(commission, name)
        models = sorted({r.model for r in rows if r.model})
        board.add_row(
            commission,
            name,
            ", ".join(models) or "-",
            str(summary.runs),
            _percent(summary.accuracy),
            _percent(summary.pass_rate),
            _money(
                _mean([r.totals.cost_usd for r in started])
                if not any("cost_usd" in r.totals.unknown_metrics for r in started)
                else None
            ),
            "-" if not started else f"{_mean([r.totals.turns for r in started]):.1f}",
            _seconds(_mean([r.seconds or 0 for r in started])),
            str(summary.scorer_failures) if summary.scorer_failures else "-",
        )
    spend = sum(r.totals.cost_usd for r in runs)
    parts: list[RenderableType] = [
        Text(f"{results.name} ({results.id})", style="bold"),
        *_agents(directory),
        board,
        Text(
            f"{len(runs)} runs, {_money(spend)} "
            + (
                "known spend (some costs unknown)"
                if any("cost_usd" in r.totals.unknown_metrics for r in runs)
                else "in all"
            ),
            style="dim",
        ),
    ]
    failed = [r for r in runs if r.score is None or not r.score.passed]
    if failed:
        table = Table("Item", "Commission", "Agent", "Why", "Run")
        for r in failed:
            table.add_row(r.item, r.commission, r.agent, why(r), str(directory / r.directory))
        parts += [Text("Runs that didn't pass", style="bold"), table]
    if results.finished is None:
        parts.append(Text("The eval stopped before every run finished.", style="yellow"))
    return Group(*parts)


def _agents(directory: Path) -> list[Text]:
    """One line per agent: its Descriptor's name and version, and its image."""
    lines = []
    for name, record in agents(directory).items():
        d = record.descriptor
        lines.append(
            Text(
                f"{name}: {d.agent_name} {d.agent_version}, image {record.image_id[:19]}",
                style="dim",
            )
        )
    return lines


def run_line(run: RunResult) -> Text:
    """One finished run, as `eval run` shows it while the others run."""
    line = Text()
    if run.score is None:
        line.append("scorer failed ", style="red")
    elif run.score.passed:
        line.append("pass ", style="green")
    else:
        line.append("fail ", style="yellow")
    line.append(f"{run.commission} / {run.agent} / {run.item}")
    if run.score is not None:
        line.append(f"  {run.score.value:.0%}")
    if run.seconds is not None:
        totals = run.totals
        line.append(
            f"  {_money(totals.cost_usd if 'cost_usd' not in totals.unknown_metrics else None)}  {totals.turns} turns  {_seconds(run.seconds)}",
            style="dim",
        )
    return line


def why(run: RunResult) -> Text:
    """Why a run didn't pass."""
    if run.score is None:
        return Text(f"scorer failed: {run.scorer_error}", style="red")
    return Text("\n".join(run.score.reasons) or "failed")


def print_scoreboard(console: Console, results: EvalResults, directory: Path) -> None:
    console.print(scoreboard(results, directory))
