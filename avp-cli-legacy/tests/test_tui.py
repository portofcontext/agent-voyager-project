"""`avp eval view`: the board picks the run, the panes follow it."""

from __future__ import annotations

import asyncio

from textual.widgets import DataTable

from avp_cli.tui import DeclScreen, EvalApp, setups_of, steps_of

TOOL = {
    "name": "bash",
    "description": "Run a shell command.",
    "params": [{"name": "cmd", "type": "string", "required": True}],
}


def _run(row_id: str, passed: bool, cost: float) -> dict:
    return {
        "row_id": row_id,
        "passed": passed,
        "total_cost_usd": cost,
        "elapsed_s": 2.0,
        "question": f"question {row_id}",
        "vessel": {"agent": "avp-pi", "model": "anthropic/claude-haiku-4-5", "tools": [TOOL]},
        "events": [
            {"type": "avp.assistant_message", "text": "thinking", "input_tokens": 10},
            {"type": "avp.tool_invoked", "tool_name": "bash", "call_id": "c1"},
            {"type": "avp.tool_returned", "tool_name": "bash", "call_id": "c1", "result": "ok"},
            {"type": "avp.assistant_message", "text": "42", "input_tokens": 12},
        ],
    }


def _payload(tasks: int) -> dict:
    return {
        "name": "demo",
        "agents": [
            {
                "agent": "avp-pi",
                "by_commission": {"pi": [_run(f"t{i}", True, 0.01) for i in range(tasks)]},
            },
            {
                "agent": "goose",
                "by_commission": {"goose": [_run(f"t{i}", i % 2 == 0, 0.02) for i in range(tasks)]},
            },
        ],
    }


def test_setups_rank_by_correct_then_cost_with_display_names():
    setups = setups_of(_payload(4))
    assert [(s.label, s.passed) for s in setups] == [("Pi", 4), ("Goose", 2)]


def test_steps_pair_calls_and_mark_the_answer():
    steps = steps_of(_run("t0", True, 0.01))
    assert len(steps) == 2
    _, returned = steps[0].calls[0]
    assert returned["result"] == "ok"
    assert steps[1].final


def test_board_cells_pick_the_run_and_tools_open_details():
    async def drive():
        app = EvalApp(_payload(3))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            board = app.query_one("#board", DataTable)
            assert board.row_count == 2 and len(board.columns) == 2 + 3 + 3
            await pilot.press("right", "down")
            await pilot.pause()
            assert (app.setups[app.setup_i].label, app.tasks[app.task_i]) == ("Goose", "t1")
            app.query_one("#equipment").focus()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, DeclScreen) and app.screen.steps == [1]

    asyncio.run(drive())


def test_many_tasks_share_one_column_and_brackets_move():
    async def drive():
        app = EvalApp(_payload(20))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            assert len(app.query_one("#board", DataTable).columns) == 2 + 1 + 3
            await pilot.press("]", "]")
            await pilot.pause()
            assert app.tasks[app.task_i] == "t2"
            await pilot.press("[", "[", "[")
            await pilot.pause()
            assert app.tasks[app.task_i] == "t19"

    asyncio.run(drive())
