"""`avp eval view`: a finished eval in the terminal.

The same shape as the shared page: a leaderboard of agents by tasks, then the
selected run as Orders, Vessel, and Log. Arrow keys move through the board;
the highlighted cell picks the run. Enter on a tool, subagent, or skill opens
its details.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

# Up to this many tasks get a named column each; more share one column of
# result marks, and `[` / `]` move between tasks.
NAMED_TASKS = 8

OK, BAD, DIM, SAIL, FOAM = "#6fdc8c", "#ef9a9a", "#9bb6c4", "#f3d28a", "#b9e6f5"

# Display names for descriptor names, as the shared page shows them.
NAMES = {
    "avp-claude-agent-sdk": "Claude Code",
    "goose": "Goose",
    "avp-codex": "Codex",
    "avp-openai-agents": "OpenAI Agents",
    "avp-pi": "Pi",
    "avp-gemini-cli": "Gemini CLI",
    "avp-deep-agents": "Deep Agents",
    "avp-pydantic-ai": "Pydantic AI",
    "avp-opencode": "OpenCode",
}


@dataclass
class Setup:
    label: str
    model: str | None
    runs: dict[str, dict[str, Any]]
    passed: int = 0
    avg_cost: float | None = None
    avg_seconds: float | None = None


@dataclass
class Step:
    n: int
    thought: dict[str, Any] | None = None
    calls: list[tuple[dict[str, Any], dict[str, Any] | None]] = field(default_factory=list)
    final: bool = False


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def setups_of(payload: dict[str, Any]) -> list[Setup]:
    """One row per agent and commission, best pass count first."""
    out: list[Setup] = []
    for agent in payload.get("agents") or [payload]:
        commissions = agent.get("by_commission") or {}
        for name, runs in commissions.items():
            agent_id = agent.get("agent") or "agent"
            label = NAMES.get(agent_id, agent_id)
            if len(commissions) > 1:
                label = f"{label} · {name}"
            model = next(((r.get("vessel") or {}).get("model") for r in runs), None)
            costs = [r["total_cost_usd"] for r in runs if r.get("total_cost_usd") is not None]
            secs = [r["elapsed_s"] for r in runs if r.get("elapsed_s")]
            out.append(
                Setup(
                    label=label,
                    model=model,
                    runs={r["row_id"]: r for r in runs},
                    passed=sum(1 for r in runs if r.get("passed") is True),
                    avg_cost=_mean(costs),
                    avg_seconds=_mean(secs),
                )
            )
    return sorted(out, key=lambda s: (-s.passed, s.avg_cost if s.avg_cost is not None else 1e9))


def tasks_of(setups: list[Setup]) -> list[str]:
    seen: dict[str, None] = {}
    for s in setups:
        for row_id in s.runs:
            seen.setdefault(row_id, None)
    return list(seen)


def steps_of(run: dict[str, Any]) -> list[Step]:
    """Each model turn with the tool calls it made, calls paired by id."""
    steps: list[Step] = []
    open_calls: dict[str, tuple[Step, int]] = {}
    for e in run.get("events") or []:
        kind = e.get("type")
        key = e.get("call_id") or e.get("tool_name") or ""
        if kind == "avp.assistant_message":
            steps.append(Step(n=len(steps) + 1, thought=e))
        elif kind == "avp.tool_invoked":
            if not steps:
                steps.append(Step(n=1))
            steps[-1].calls.append((e, None))
            open_calls[key] = (steps[-1], len(steps[-1].calls) - 1)
        elif kind == "avp.tool_returned" and key in open_calls:
            step, i = open_calls.pop(key)
            step.calls[i] = (step.calls[i][0], e)
    if steps and steps[-1].thought and not steps[-1].calls:
        steps[-1].final = True
    return steps


def money(x: float | None) -> str:
    if x is None:
        return "—"
    return f"${x:.4f}" if x < 0.01 else f"${x:.3f}"


def mark(run: dict[str, Any] | None) -> Text:
    if run is None:
        return Text("")
    if run.get("passed") is True:
        return Text("✓", style=f"bold {OK}")
    if run.get("passed") is False:
        return Text("✗", style=f"bold {BAD}")
    return Text("·", style=DIM)


def route(run: dict[str, Any]) -> Text:
    """The run's route on one line: ✦ model turns, • tool calls, then the verdict."""
    out = Text()
    for step in steps_of(run):
        if step.thought:
            out.append("✦", style=SAIL if step.final else FOAM)
            out.append("─", style=DIM)
        for _, ret in step.calls:
            out.append("•", style=BAD if ret and ret.get("is_error") else SAIL)
            out.append("─", style=DIM)
    out.append_text(mark(run) if run.get("passed") is not None else Text("■", style=DIM))
    return out


def uses_of(run: dict[str, Any]) -> dict[str, list[int]]:
    uses: dict[str, list[int]] = {}
    for step in steps_of(run):
        for inv, _ in step.calls:
            uses.setdefault(inv.get("tool_name") or "?", []).append(step.n)
    return uses


class DeclScreen(ModalScreen[None]):
    """A tool, subagent, or skill: what it is, its parameters, and its uses."""

    BINDINGS = [Binding("escape,q,enter", "dismiss", "Close")]
    DEFAULT_CSS = """
    DeclScreen { align: center middle; }
    #decl { width: 90; max-width: 95%; max-height: 85%; border: round $warning; padding: 1 2; background: $panel; }
    """

    def __init__(self, decl: dict[str, Any], kind: str, steps: list[int]) -> None:
        super().__init__()
        self.decl, self.kind, self.steps = decl, kind, steps

    def compose(self) -> ComposeResult:
        d = self.decl
        body = Text()
        body.append(d["name"], style=f"bold {FOAM}")
        origin = f"MCP · {d['mcp_server_id']}" if d.get("mcp_server_id") else "Built in"
        body.append(f"   {self.kind} · {origin}\n\n", style=DIM)
        if d.get("description"):
            body.append(d["description"] + "\n\n")
        if d.get("params"):
            body.append("PARAMETERS\n", style=f"bold {SAIL}")
            for p in d["params"]:
                body.append(f"  {p['name']}", style=FOAM)
                if p.get("type"):
                    body.append(f"  {p['type']}", style=DIM)
                if p.get("required"):
                    body.append("  required", style=SAIL)
                body.append("\n")
                if p.get("description"):
                    body.append(f"    {p['description']}\n", style=DIM)
            body.append("\n")
        if self.kind == "tool":
            if self.steps:
                body.append(f"USED {len(self.steps)}×", style=f"bold {SAIL}")  # noqa: RUF001
                body.append("  steps " + ", ".join(str(n) for n in self.steps), style=DIM)
            else:
                body.append("NOT USED", style=f"bold {DIM}")
        yield VerticalScroll(Static(body), id="decl")


class EvalApp(App[None]):
    TITLE = "avp eval view"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("[", "task(-1)", "Prev task", show=False),
        Binding("]", "task(1)", "Next task", show=False),
        Binding("tab", "focus_next", "Next pane"),
    ]
    CSS = """
    #board { height: auto; max-height: 45%; }
    #brief { height: auto; max-height: 14; }
    #orders, #vessel { width: 1fr; border: round $primary-darken-2; padding: 0 1; height: auto; max-height: 14; }
    #orders { border-title-color: #f3d28a; }
    #vessel { border-title-color: #f3d28a; }
    #log { border: round $primary-darken-2; padding: 0 1; border-title-color: #f3d28a; }
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__()
        self.payload = payload
        self.setups = setups_of(payload)
        self.tasks = tasks_of(self.setups)
        self.named = len(self.tasks) <= NAMED_TASKS
        self.setup_i = 0
        self.task_i = 0
        self.decls: list[tuple[str, dict[str, Any]]] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="board", cursor_type="cell", zebra_stripes=False)
        with Horizontal(id="brief"):
            yield Static(id="orders")
            with Vertical(id="vessel"):
                yield Static(id="vessel-head")
                yield OptionList(id="equipment")
        yield VerticalScroll(Static(id="log-body"), id="log")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = self.payload.get("name") or ""
        for pane, title in (("orders", "Orders"), ("vessel", "Vessel"), ("log", "Log")):
            self.query_one(f"#{pane}").border_title = title
        table = self.query_one("#board", DataTable)
        task_cols = self.tasks if self.named else [f"Tasks ({len(self.tasks)})"]
        table.add_columns("Agent", "Model", *task_cols, "Correct", "Cost / task", "Time / task")
        self._fill_board()
        table.move_cursor(row=0, column=2)
        self._show()

    def _fill_board(self) -> None:
        table = self.query_one("#board", DataTable)
        table.clear()
        for s in self.setups:
            if self.named:
                cells = [mark(s.runs.get(t)) for t in self.tasks]
            else:
                strip = Text()
                for i, t in enumerate(self.tasks):
                    r = s.runs.get(t)
                    style = (
                        OK
                        if r and r.get("passed")
                        else BAD
                        if r and r.get("passed") is False
                        else DIM
                    )
                    strip.append(
                        "■" if i == self.task_i else "▪",
                        style=f"bold {style}" if i == self.task_i else style,
                    )
                cells = [strip]
            total = len(s.runs)
            table.add_row(
                Text(s.label, style=f"bold {FOAM}"),
                Text((s.model or "—").split("/")[-1], style=DIM),
                *cells,
                Text(f"{s.passed}/{total}", style=OK if s.passed == total else "#e6b450"),
                Text(money(s.avg_cost), style=SAIL),
                Text(f"{s.avg_seconds:.1f}s" if s.avg_seconds else "—", style=DIM),
            )

    def on_data_table_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        row, col = event.coordinate.row, event.coordinate.column
        self.setup_i = row
        if self.named and 2 <= col < 2 + len(self.tasks):
            self.task_i = col - 2
        self._show()

    def action_task(self, delta: int) -> None:
        if not self.tasks:
            return
        self.task_i = (self.task_i + delta) % len(self.tasks)
        table = self.query_one("#board", DataTable)
        cursor = table.cursor_coordinate
        self._fill_board()
        if self.named:
            table.move_cursor(row=cursor.row, column=2 + self.task_i)
        else:
            table.move_cursor(row=cursor.row, column=cursor.column)
        self._show()

    def _run(self) -> dict[str, Any] | None:
        if not self.setups or not self.tasks:
            return None
        return self.setups[self.setup_i].runs.get(self.tasks[self.task_i])

    def _show(self) -> None:
        run = self._run()
        orders = self.query_one("#orders", Static)
        head = self.query_one("#vessel-head", Static)
        equipment = self.query_one("#equipment", OptionList)
        log = self.query_one("#log-body", Static)
        equipment.clear_options()
        self.decls = []
        task = self.tasks[self.task_i] if self.tasks else ""
        self.query_one("#orders").border_title = f"Orders · {task}"
        if run is None:
            orders.update(Text("No run for this task.", style=DIM))
            head.update("")
            log.update("")
            return

        o = run.get("orders") or {}
        text = Text()
        text.append(
            (run.get("question") or o.get("task") or "Task not recorded.") + "\n", style="bold"
        )
        if run.get("expected") is not None:
            text.append("Expected  ", style=DIM)
            text.append(f"{run['expected']}\n", style=SAIL)
        allowed = o.get("allowed_tools")
        if allowed is not None:
            names = [n for v in allowed.values() for n in v]
            text.append("Allowed tools  ", style=DIM)
            text.append((", ".join(names) or "none") + "\n")
        orders.update(text)

        v = run.get("vessel") or {}
        vh = Text()
        name = v.get("agent")
        vh.append(
            NAMES.get(name, name) if name else self.setups[self.setup_i].label, style=f"bold {FOAM}"
        )
        if v.get("version"):
            vh.append(f" v{v['version']}", style=DIM)
        if v.get("model"):
            vh.append(f"  {v['model'].split('/')[-1]}", style=SAIL)
        head.update(vh)
        uses = uses_of(run)
        for kind, key in (("tool", "tools"), ("subagent", "subagents"), ("skill", "skills")):
            items = sorted(v.get(key) or [], key=lambda d: -len(uses.get(d["name"], [])))
            for d in items:
                n = len(uses.get(d["name"], [])) if kind == "tool" else 0
                label = Text()
                label.append(f"{kind[0].upper()} ", style=DIM)
                label.append(d["name"], style=f"bold {SAIL}" if n else "")
                if n:
                    label.append(f" ×{n}", style=SAIL)  # noqa: RUF001
                equipment.add_option(Option(label))
                self.decls.append((kind, d))
        if self.decls:
            equipment.highlighted = 0

        body = Text()
        body.append_text(route(run))
        body.append("\n\n")
        for step in steps_of(run):
            body.append(f"{step.n:>3}  ", style=DIM)
            t = step.thought
            if t:
                body.append(
                    "Answer" if step.final else "Thinking", style=SAIL if step.final else FOAM
                )
                tokens = (t.get("input_tokens") or 0) + (t.get("output_tokens") or 0)
                body.append(f"  {tokens:,} tokens · {money(t.get('cost_usd'))}\n", style=DIM)
                if t.get("text"):
                    body.append("     " + t["text"].strip().replace("\n", "\n     ") + "\n")
            else:
                body.append("\n")
            for inv, ret in step.calls:
                err = bool(ret and ret.get("is_error"))
                body.append(f"     ⚙ {inv.get('tool_name')}", style=f"bold {BAD if err else SAIL}")
                if err:
                    body.append("  error", style=BAD)
                body.append("\n")
                if inv.get("tool_input") is not None:
                    raw = inv["tool_input"]
                    vals = list(raw.values()) if isinstance(raw, dict) else []
                    shown = (
                        vals[0]
                        if len(vals) == 1 and isinstance(vals[0], str)
                        else json.dumps(raw, indent=2)
                    )
                    body.append(
                        "       " + shown.strip().replace("\n", "\n       ") + "\n", style=DIM
                    )
                if ret and ret.get("result"):
                    body.append(
                        "       → " + ret["result"].strip().replace("\n", "\n         ") + "\n",
                        style=BAD if err else OK,
                    )
            body.append("\n")
        for e in run.get("events") or []:
            if e.get("type") == "avp.error_occurred":
                body.append(f"⚠ {e.get('error_code')}: {e.get('error_message')}\n", style=BAD)
        verdict = {True: ("✓ Correct", OK), False: ("✗ Incorrect", BAD)}.get(
            run.get("passed"), ("Not scored", DIM)
        )
        body.append(verdict[0], style=f"bold {verdict[1]}")
        if run.get("verdict"):
            body.append(f"\n{run['verdict']}", style=DIM)
        log.update(body)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        kind, decl = self.decls[event.option_index]
        run = self._run() or {}
        self.push_screen(DeclScreen(decl, kind, uses_of(run).get(decl["name"], [])))
