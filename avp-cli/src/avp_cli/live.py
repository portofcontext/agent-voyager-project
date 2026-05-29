"""Live, in-place progress for a running eval: the inline voyage.

The current run animates on one line — a growing voyage of brand-colored glyphs
(one per turn / tool) plus a live turn count, current tool, and running cost.
Finished runs collapse to a single summary line above it. Built on `rich.Live`
over stderr, so the board on stdout stays clean and scrollback stays compact
(one line per finished run, not one per event).
"""

from __future__ import annotations

from typing import Any

from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from avp import trajectory as T
from avp_cli import brand, console
from avp_cli.eval.engine import RunObserver, RunResult
from avp_cli.observability import tool_tally


class VoyageLive:
    """Context manager that renders an eval's progress as it runs.

    When `compare` is set (more than one agent), each run's summary names its
    agent and a head-to-head line prints after every agent finishes a task.
    """

    def __init__(self, header_label: str, total: int, *, compare: bool = False) -> None:
        self._label = header_label
        self._total = total
        self._compare = compare
        self._live = Live(console=console.err, refresh_per_second=12, transient=True)
        self._spinner = Spinner("dots", style=brand.SAIL)
        self._cur: dict[str, Any] | None = None

    def __enter__(self) -> VoyageLive:
        console.err.print(f"[dim]running {self._total} runs · {self._label}[/dim]")
        self._live.__enter__()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._live.update(Text(""))
        self._live.__exit__(*exc)

    def observer(self) -> RunObserver:
        return RunObserver(
            on_start=self._on_start,
            on_event=self._on_event,
            on_end=self._on_end,
            on_compare=self._on_compare if self._compare else None,
        )

    # ── callbacks ────────────────────────────────────────────────────────────

    def _on_start(self, n: int, total: int, agent: str, setup: str, item: str) -> None:
        self._cur = {
            "agent": agent,
            "setup": setup,
            "item": item,
            "glyphs": [],
            "turns": 0,
            "cost": 0.0,
            "tool": None,
            "turn_idx": None,  # index of the current turn's glyph, so a tool upgrades it
        }
        self._render()

    def _on_event(self, ev: Any) -> None:
        c = self._cur
        if c is None:
            return
        # One glyph per turn: a turn starts as ● (text) and is upgraded to ◆ the
        # moment it invokes a tool. So the voyage length equals the turn count.
        if isinstance(ev, T.AssistantMessageEvent):
            c["turns"] += 1
            c["cost"] += ev.data.cost_usd
            c["tool"] = None
            c["glyphs"].append(("●", brand.MAST))
            c["turn_idx"] = len(c["glyphs"]) - 1
        elif isinstance(ev, T.ToolInvokedEvent):
            c["tool"] = ev.data.tool_name
            if c["turn_idx"] is not None:
                c["glyphs"][c["turn_idx"]] = ("◆", brand.SAIL)
            else:
                c["glyphs"].append(("◆", brand.SAIL))
        elif isinstance(ev, T.ErrorOccurredEvent):
            c["glyphs"].append(("✖", "#e25a4d"))
            c["turn_idx"] = None
        self._render()

    def _on_end(self, n: int, total: int, agent: str, result: RunResult) -> None:
        # Permanent one-line summary above the live region; then clear it.
        self._live.console.print(self._summary(agent, result))
        self._cur = None
        self._live.update(Text(""))

    def _on_compare(self, setup: str, item: str, pairs: list[tuple[str, RunResult]]) -> None:
        self._live.console.print(self._head_to_head(setup, item, pairs))

    # ── rendering ──────────────────────────────────────────────────────────────

    def _render(self) -> None:
        c = self._cur
        if c is None:
            return
        line = Text()
        line.append(f"{brand.SAILBOAT} ", style=brand.SAIL)
        if self._compare:
            line.append(f"{c['agent']} · ", style=brand.SKY)
        line.append(f"{c['setup']} / {c['item']}  ", style=brand.MAST)
        if c["glyphs"]:
            for g, color in c["glyphs"]:
                line.append(g, style=color)
                line.append(" ", style="dim")
        else:
            line.append("setting sail", style="dim")
        line.append("  ", style="dim")
        line.append(f"turn {c['turns']}", style="#7fa0b3")
        if c["tool"]:
            line.append(f" · {c['tool']}", style=brand.SAIL)
        line.append(f" · ${c['cost']:.4f}", style="#7fa0b3")
        grid = Table.grid(padding=(0, 1))
        grid.add_row(self._spinner, line)
        self._live.update(grid)

    def _summary(self, agent: str, r: RunResult) -> Text:
        line = Text()
        if r.spawn_error is not None:
            line.append("✖ ", style="#e25a4d")
            if self._compare:
                line.append(f"{agent} · ", style=brand.SKY)
            line.append(f"{r.setup_name} / {r.item_id}  ", style=brand.MAST)
            line.append(r.spawn_error, style="#e25a4d")
            return line
        passed = bool(r.score and r.score.passed)
        line.append("✓ " if passed else "· ", style="green" if passed else "#7fa0b3")
        if self._compare:
            line.append(f"{agent} · ", style=brand.SKY)
        line.append(f"{r.setup_name} / {r.item_id}  ", style=brand.MAST)
        if r.score is not None:
            line.append(f"{r.score.value:.0%}", style="green" if passed else brand.SAIL)
        if r.summary is not None:
            line.append(f"   {r.summary.total_turns} turns", style="#7fa0b3")
            line.append(f"   ${r.summary.total_cost_usd:.4f}", style="#7fa0b3")
            tally = tool_tally(r.summary)
            if tally:
                line.append(f"   {tally}", style="#5a8294")
        return line

    def _head_to_head(self, setup: str, item: str, pairs: list[tuple[str, RunResult]]) -> Text:
        """A one-line head-to-head: ⚖ setup/item   agentA …   ·   agentB …"""
        winner = _winner(pairs)
        line = Text()
        line.append("⚖ ", style=brand.SAIL)
        line.append(f"{setup} / {item}   ", style=brand.MAST)
        for i, (agent, r) in enumerate(pairs):
            if i:
                line.append("   ·   ", style="#2c4456")
            is_win = agent == winner
            line.append(agent, style="bold green" if is_win else "#9fb4c2")
            if r.spawn_error is not None:
                line.append(" err", style="#e25a4d")
                continue
            acc = f" {r.score.value:.0%}" if r.score else " —"
            line.append(acc, style="green" if is_win else "#9fb4c2")
            if r.summary is not None:
                line.append(f" ${r.summary.total_cost_usd:.4f}", style="#7fa0b3")
                line.append(f" {r.summary.total_turns}t", style="#7fa0b3")
        return line


def _winner(pairs: list[tuple[str, RunResult]]) -> str | None:
    """Pick the head-to-head winner: highest accuracy, then lowest cost."""
    ranked = sorted(
        pairs,
        key=lambda p: (
            -(p[1].score.value if p[1].score else -1.0),
            p[1].summary.total_cost_usd if p[1].summary else float("inf"),
        ),
    )
    return ranked[0][0] if ranked else None
