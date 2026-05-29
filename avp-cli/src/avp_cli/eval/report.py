"""Render a `Board`: a rich leaderboard table for humans, a JSON dump for
post-processing.

The JSON dump carries per-setup metrics plus, per run, a pointer to its NDJSON
trajectory, so a benchmark write-up has the numbers and the raw evidence in one
file (and aligns with the platform's `/api/evals/{name}` shape).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.table import Table

from avp_cli.eval.engine import Board


def _accuracy_style(value: float) -> str:
    if value >= 0.9:
        return "bold green"
    if value >= 0.7:
        return "green"
    if value >= 0.5:
        return "yellow"
    return "red"


def board_table(board: Board) -> Table:
    """The ranked leaderboard as a rich Table."""
    n_items = len(board.rows[0].results) if board.rows else 0
    table = Table(
        title=f"avp eval · {board.dataset_name} · {n_items} items · agent={board.agent_label}",
        title_style="bold",
        caption=(
            f"{len(board.rows)} setups · {board.total_runs} runs · "
            f"total spend ${board.total_cost:.4f} · trajectories in {board.out_dir}/"
        ),
        header_style="bold",
    )
    table.add_column("#", justify="right", style="dim")
    table.add_column("commission")
    table.add_column("accuracy", justify="right")
    table.add_column("pass_rate", justify="right")
    table.add_column("$/run", justify="right")
    table.add_column("turns/run", justify="right")
    for i, row in enumerate(board.rows, start=1):
        errored = f"  [red]({row.n_errors} errored)[/red]" if row.n_errors else ""
        table.add_row(
            str(i),
            f"{row.name}{errored}",
            f"[{_accuracy_style(row.accuracy)}]{row.accuracy:.0%}[/]",
            f"{row.pass_rate:.0%}",
            f"${row.cost_per_run:.4f}",
            f"{row.turns_per_run:.1f}",
        )
    return table


def comparison_table(boards: list[Board]) -> Table:
    """Head-to-head: commissions as rows, one accuracy/$ pair per agent column.

    The highest-accuracy agent's cell per commission is highlighted; the caption
    gives each agent's overall mean accuracy and $/run.
    """
    agents = [b.agent_label for b in boards]
    # commission -> agent -> SetupRow
    by_commission: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for b in boards:
        for row in b.rows:
            if row.name not in by_commission:
                by_commission[row.name] = {}
                order.append(row.name)
            by_commission[row.name][b.agent_label] = row

    n_items = len(boards[0].rows[0].results) if boards and boards[0].rows else 0
    table = Table(
        title=f"head-to-head · {boards[0].dataset_name} · {n_items} items",
        title_style="bold",
        header_style="bold",
        caption=" · ".join(
            f"{b.agent_label}: {_mean_acc(b):.0%} acc, ${_mean_cost(b):.4f}/run" for b in boards
        ),
    )
    table.add_column("commission")
    for a in agents:
        table.add_column(a, justify="right")
    for commission_name in order:
        cells = by_commission[commission_name]
        best = max(
            (a for a in agents if a in cells),
            key=lambda a: cells[a].accuracy,
            default=None,
        )
        rendered = [commission_name]
        for a in agents:
            row = cells.get(a)
            if row is None:
                rendered.append("[dim]—[/dim]")
                continue
            style = "bold green" if a == best else _accuracy_style(row.accuracy)
            rendered.append(f"[{style}]{row.accuracy:.0%}[/]  [#7fa0b3]${row.cost_per_run:.4f}[/]")
        table.add_row(*rendered)
    return table


def _mean_acc(board: Board) -> float:
    return sum(r.accuracy for r in board.rows) / len(board.rows) if board.rows else 0.0


def _mean_cost(board: Board) -> float:
    return sum(r.cost_per_run for r in board.rows) / len(board.rows) if board.rows else 0.0


def failures(board: Board) -> list[str]:
    """One line per failed / errored run, for a diagnostics panel."""
    out: list[str] = []
    for row in board.rows:
        for r in row.results:
            if r.spawn_error is not None:
                out.append(f"{row.name} / {r.item_id}: run error: {r.spawn_error}")
            elif not r.passed:
                detail = r.score.detail if r.score else "no score"
                out.append(f"{row.name} / {r.item_id}: {detail}")
    return out


def board_to_dict(board: Board) -> dict:
    return {
        "dataset": board.dataset_name,
        "agent": board.agent_label,
        "generated_at": datetime.now(UTC).isoformat(),
        "trajectories_dir": board.out_dir,
        "commissions": [
            {
                "rank": i,
                "name": row.name,
                "description": row.description,
                "model": row.model,
                "accuracy": row.accuracy,
                "pass_rate": row.pass_rate,
                "cost_per_run": row.cost_per_run,
                "turns_per_run": row.turns_per_run,
                "n_items": row.n_items,
                "n_errors": row.n_errors,
                "runs": [
                    {
                        "item_id": r.item_id,
                        "score": (
                            None
                            if r.score is None
                            else {
                                "value": r.score.value,
                                "passed": r.score.passed,
                                "detail": r.score.detail,
                            }
                        ),
                        "cost_usd": r.summary.total_cost_usd if r.summary else None,
                        "turns": r.summary.total_turns if r.summary else None,
                        "tokens": r.summary.total_tokens if r.summary else None,
                        "stop_reason": r.summary.stop_reason if r.summary else None,
                        "output_text": r.output.text if r.output else None,
                        "spawn_error": r.spawn_error,
                        "trajectory_path": r.trajectory_path,
                    }
                    for r in row.results
                ],
            }
            for i, row in enumerate(board.rows, start=1)
        ],
    }


def dump_json(board: Board, path: str | Path) -> None:
    Path(path).write_text(json.dumps(board_to_dict(board), indent=2) + "\n")
