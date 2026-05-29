"""Tests for the eval engine: setups, output extraction, scoring, board, report.

Most are pure unit tests. One crosses the supervisor↔agent subprocess seam
(`run_eval` driving a scripted inline agent with no LLM), which is the seam the
repo flags as where bugs hide.
"""

from __future__ import annotations

import json
import sys

import pytest

from avp.commission import Commission
from avp.content import TextBlock
from avp.envelope import ZERO_SPAN_ID, new_span_id, new_trace_id
from avp.trajectory import (
    AgentStoppedData,
    AgentStoppedEvent,
    AssistantMessageData,
    AssistantMessageEvent,
    StopReason,
    ToolInvokedData,
    ToolInvokedEvent,
    Usage,
)
from avp_cli import (
    Dataset,
    ExactMatchScorer,
    Item,
    Setup,
    StructuralMatchScorer,
    Summary,
    board_table,
    extract_final_output,
    run_eval,
)
from avp_cli.eval.engine import Eval, RunResult, _aggregate, rank_rows
from avp_cli.eval.report import board_to_dict
from avp_cli.eval.scoring import FinalOutput

# ── Setup → Commission compilation ────────────────────────────────────────────


def _setup(id_: str, **fields) -> Setup:
    """A Setup wrapping a base wire Commission (run_id defaults to the id)."""
    return Setup(id=id_, commission=Commission(schema_version="0.1", run_id=id_, **fields))


def test_setup_to_commission_carries_the_variant_surface() -> None:
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    setup = _setup(
        "terse",
        prompt="Return JSON for: {input}",
        enabled_builtin_tools=["read_file"],
        output_schema=schema,
        model="claude-haiku-4-5",
    )
    item = Item(id="i1", prompt="Paris, France")
    c = setup.to_commission(item, run_id="terse-i1")

    assert c.run_id == "terse-i1"
    assert c.prompt == "Return JSON for: Paris, France"  # {input} filled with the case
    assert c.enabled_builtin_tools == ["read_file"]
    assert c.output_schema == schema
    assert c.model == "claude-haiku-4-5"  # the commission's own model
    assert c.supervisor is not None and c.supervisor.name == "avp-cli"
    assert "commission:terse" in (c.tags or [])


def test_model_override_wins_over_commission_model() -> None:
    # The run-time --model flag overrides every commission's own model.
    setup = _setup("terse", model="claude-haiku-4-5")
    c = setup.to_commission(
        Item(id="i1", prompt="x"), run_id="r", model_override="claude-sonnet-4-6"
    )
    assert c.model == "claude-sonnet-4-6"


def test_setup_uses_item_prompt_when_no_template() -> None:
    c = _setup("baseline").to_commission(
        Item(id="i1", prompt="raw task"), run_id="r", model_override="m"
    )
    assert c.prompt == "raw task"
    assert c.model == "m"  # override applies when the commission has no model of its own


# ── Final-output extraction ───────────────────────────────────────────────────


def _span(parent: str = ZERO_SPAN_ID) -> dict:
    return {"trace_id": new_trace_id(), "span_id": new_span_id(), "parent_span_id": parent}


def _assistant(text: str) -> AssistantMessageEvent:
    return AssistantMessageEvent(
        subject="r",
        data=AssistantMessageData(
            **_span(),
            step=1,
            duration_ms=1,
            content=[TextBlock(text=text)],
            usage=Usage(input_tokens=1, output_tokens=1),
            cost_usd=0.0,
        ),
    )


def _stopped(output: object) -> AgentStoppedEvent:
    return AgentStoppedEvent(
        subject="r",
        data=AgentStoppedData(**_span(), reason=StopReason.converged, output=output),
    )


def _tool(name: str, tool_input: dict) -> ToolInvokedEvent:
    return ToolInvokedEvent(
        subject="r",
        data=ToolInvokedData(
            **_span(), step=1, tool_call_id="c1", tool_name=name, tool_input=tool_input
        ),
    )


def test_extract_prefers_agent_stopped_output_over_last_assistant() -> None:
    events = [_assistant("chatter"), _stopped('{"city": "Paris"}')]
    out = extract_final_output(events)
    assert out.text == '{"city": "Paris"}'
    assert out.structured == {"city": "Paris"}
    assert out.stop_reason == "converged"


def test_extract_falls_back_to_last_assistant_text() -> None:
    events = [_assistant("first"), _assistant("the answer"), _stopped(None)]
    out = extract_final_output(events)
    assert out.text == "the answer"


def test_extract_parses_fenced_json() -> None:
    out = extract_final_output([_stopped('```json\n{"a": 1}\n```')])
    assert out.structured == {"a": 1}


def test_extract_finds_json_fenced_inside_prose() -> None:
    # Claude Code often answers conversationally with the JSON in a fence.
    prose = 'Done! Here it is:\n```json\n{"city": "Tokyo", "n": 14}\n```'
    out = extract_final_output([_assistant(prose), _stopped("")])
    assert out.structured == {"city": "Tokyo", "n": 14}


def test_extract_reads_structured_output_tool_call() -> None:
    # The Claude Agent SDK routes output_schema through a StructuredOutput tool
    # call; the answer is its input, and the final text may be empty.
    answer = {"city": "Paris", "country": "France", "population_millions": 2}
    events = [_tool("StructuredOutput", answer), _assistant(""), _stopped("")]
    out = extract_final_output(events)
    assert out.structured == answer


def test_extract_skips_trailing_empty_assistant_message() -> None:
    out = extract_final_output([_assistant("the answer"), _assistant(""), _stopped(None)])
    assert out.text == "the answer"


# ── Scorers ────────────────────────────────────────────────────────────────────


def _summary() -> Summary:
    return Summary(run_id="r", stop_reason="converged", total_turns=1, total_cost_usd=0.001)


def test_exact_match_scorer_normalizes() -> None:
    s = ExactMatchScorer()
    item = Item(id="i", prompt="", expected="All Done")
    assert s.score(item, FinalOutput("  all   done ", None, "converged"), _summary()).passed


def test_structural_scorer_partial_credit_does_not_pass_at_threshold_one() -> None:
    s = StructuralMatchScorer(threshold=1.0)
    item = Item(id="i", prompt="", expected={"city": "Paris", "country": "France", "pop": 2})
    # 2 of 3 keys right → value 0.666..., passed False at threshold 1.0
    out = FinalOutput(None, {"city": "Paris", "country": "France", "pop": 99}, "converged")
    score = s.score(item, out, _summary())
    assert round(score.value, 2) == 0.67
    assert score.passed is False
    assert "pop" in score.detail


def test_structural_scorer_full_credit_passes() -> None:
    s = StructuralMatchScorer(threshold=1.0)
    item = Item(id="i", prompt="", expected={"city": "Paris", "pop": 2})
    out = FinalOutput(None, {"city": "paris", "pop": 2.0}, "converged")  # case + 2==2.0
    assert s.score(item, out, _summary()).passed


def test_fidelity_scores_cell_content_not_markup_chrome() -> None:
    # A content-correct table wrapped in a styled HTML document + a ```html fence
    # + prose, with different-but-equivalent tags, must score on its cell text,
    # not be punished for the chrome. (Regression: raw token_set_ratio over the
    # markup scored a perfect extraction ~0.6 because of the tag/CSS noise.)
    pytest.importorskip("rapidfuzz")
    from avp_cli.eval.scoring import FidelityScorer

    ref = "<table><tr><th>City</th><th>Pop</th></tr><tr><td>Paris</td><td>2M</td></tr></table>"
    chromed = (
        "Sure, here it is:\n```html\n<!DOCTYPE html><html><head>"
        "<style>td{color:red;font-family:Arial}</style></head><body>"
        '<table border="1" class="data"><tr><th>City</th><th>Pop</th></tr>'
        "<tr><td>Paris</td><td>2M</td></tr></table></body></html>\n```"
    )
    s = FidelityScorer(threshold=0.8)
    item = Item(id="i", prompt="", expected=ref)
    good = s.score(item, FinalOutput(chromed, None, "converged"), _summary())
    assert good.value >= 0.95 and good.passed

    wrong = "<table><tr><th>City</th><th>Pop</th></tr><tr><td>Berlin</td><td>9M</td></tr></table>"
    bad = s.score(item, FinalOutput(wrong, None, "converged"), _summary())
    assert not bad.passed  # wrong cell content still fails


# ── Board aggregation + ranking ────────────────────────────────────────────────


def _result(
    setup: str, item: str, value: float, passed: bool, cost: float, turns: int
) -> RunResult:
    from avp_cli.eval.scoring import Score

    return RunResult(
        setup_name=setup,
        item_id=item,
        score=Score(value=value, passed=passed),
        summary=Summary(run_id=f"{setup}-{item}", total_turns=turns, total_cost_usd=cost),
        output=FinalOutput("x", None, "converged"),
        trajectory_path=f"/tmp/{setup}-{item}.ndjson",
    )


def test_board_aggregation_math() -> None:
    setup = _setup("s", model="m")
    results = [
        _result("s", "i1", 1.0, True, 0.002, 2),
        _result("s", "i2", 0.5, False, 0.004, 4),
    ]
    row = _aggregate(setup, results)
    assert row.n_items == 2
    assert row.n_errors == 0
    assert row.accuracy == 0.75  # mean(1.0, 0.5)
    assert row.pass_rate == 0.5  # 1 of 2
    assert round(row.cost_per_run, 4) == 0.003
    assert row.turns_per_run == 3.0


def test_board_counts_spawn_errors_as_zero_score() -> None:
    setup = _setup("s")
    results = [
        _result("s", "i1", 1.0, True, 0.002, 2),
        RunResult(setup_name="s", item_id="i2", spawn_error="boom"),
    ]
    row = _aggregate(setup, results)
    assert row.n_errors == 1
    assert row.accuracy == 0.5  # mean(1.0, 0.0)
    assert row.pass_rate == 0.5
    assert row.cost_per_run == 0.002  # only the run that produced a summary


def test_rank_orders_by_accuracy_then_pass_rate_then_cost() -> None:
    def row(name: str, acc: float, pr: float, cost: float):
        return _aggregate(_setup(name), [_result(name, "i", acc, pr >= 1.0, cost, 1)])

    ranked = rank_rows([row("low", 0.5, 0.0, 0.001), row("high", 1.0, 1.0, 0.009)])
    assert [r.name for r in ranked] == ["high", "low"]


# ── Report rendering ───────────────────────────────────────────────────────────


def test_render_and_dump_round_trip() -> None:
    from io import StringIO

    from rich.console import Console

    from avp_cli.eval.engine import Board

    setup = _setup("winner", model="m")
    board_rows = [_aggregate(setup, [_result("winner", "i1", 1.0, True, 0.002, 2)])]
    board = Board(dataset_name="d", agent_label="ref", out_dir="/tmp/x", rows=board_rows)

    buf = StringIO()
    Console(file=buf, width=120).print(board_table(board))
    text = buf.getvalue()
    assert "winner" in text
    assert "accuracy" in text

    d = board_to_dict(board)
    assert d["commissions"][0]["name"] == "winner"
    assert d["commissions"][0]["runs"][0]["trajectory_path"].endswith(".ndjson")
    # the dict must be JSON-serializable
    json.dumps(d)


# ── Seam: run_eval drives a real agent's run contract (no LLM) ─────────────────

# A dependency-free agent honoring the AVP run contract
# (`run --commission <path> --out <path>`), emitting a canned trajectory. This
# is exactly how the conformance harness drives Goose and Claude Code, so the
# test crosses the supervisor↔agent subprocess seam without an LLM.
_INLINE_AGENT = """\
import argparse, json
from pathlib import Path

from avp.commission import Commission
from avp.content import TextBlock, ToolResultBlock
from avp.envelope import ZERO_SPAN_ID, new_span_id, new_trace_id
from avp.trajectory import (
    AgentStoppedData, AgentStoppedEvent,
    AssistantMessageData, AssistantMessageEvent,
    StopReason, ToolInvokedData, ToolInvokedEvent,
    ToolReturnedData, ToolReturnedEvent, Usage,
)

p = argparse.ArgumentParser()
p.add_argument("cmd")
p.add_argument("--commission", required=True)
p.add_argument("--out", required=True)
a = p.parse_args()

commission = Commission.model_validate(json.loads(Path(a.commission).read_text()))
rid = commission.run_id
trace, agent_span = new_trace_id(), new_span_id()

def span(parent):
    return {"trace_id": trace, "span_id": new_span_id(), "parent_span_id": parent}

turn = span(agent_span)
events = [
    AssistantMessageEvent(
        subject=rid,
        data=AssistantMessageData(
            **turn, step=1, duration_ms=1,
            content=[TextBlock(text="working")],
            usage=Usage(input_tokens=10, output_tokens=5), cost_usd=0.001,
        ),
    ),
    ToolInvokedEvent(
        subject=rid,
        data=ToolInvokedData(
            **span(turn["span_id"]), step=1, tool_call_id="c1",
            tool_name="read_file", tool_input={"path": "x"},
        ),
    ),
    ToolReturnedEvent(
        subject=rid,
        data=ToolReturnedData(
            **span(turn["span_id"]), step=1, tool_call_id="c1", tool_name="read_file",
            duration_ms=1, tool_result=ToolResultBlock(tool_use_id="c1", content="ok"),
        ),
    ),
    AgentStoppedEvent(
        subject=rid,
        data=AgentStoppedData(**span(ZERO_SPAN_ID), reason=StopReason.converged, output="all done"),
    ),
]
Path(a.out).write_text("\\n".join(e.model_dump_json(by_alias=True, exclude_none=True) for e in events) + "\\n")
"""


def test_run_eval_drives_a_scripted_agent_end_to_end(tmp_path) -> None:
    from avp_conformance.manifest import AgentManifest

    from avp_cli.agents import ResolvedAgent

    agent_script = tmp_path / "tiny_agent.py"
    agent_script.write_text(_INLINE_AGENT)
    out_dir = tmp_path / "runs"

    agent = ResolvedAgent(
        name="scripted",
        manifest=AgentManifest(command=[sys.executable, str(agent_script)]),
        manifest_cwd=tmp_path,
    )
    ev = Eval(
        setups=[_setup("solo")],
        dataset=Dataset(name="d", items=[Item(id="i1", prompt="anything", expected="all done")]),
        scorer=ExactMatchScorer(),
    )

    board = run_eval(ev, agent=agent, out_dir=out_dir)

    assert len(board.rows) == 1
    row = board.rows[0]
    assert row.name == "solo"
    assert row.accuracy == 1.0
    assert row.pass_rate == 1.0
    assert row.n_errors == 0
    assert board.interrupted is False
    # the agent wrote its raw trajectory under out_dir for inspection
    assert (out_dir / "scripted-solo-i1.ndjson").exists()


def test_run_eval_streams_events_to_observer(tmp_path) -> None:
    """With an observer.on_event, run_agent tails the trajectory and the engine
    feeds each event through — the live-progress seam, no LLM."""
    from avp_conformance.manifest import AgentManifest

    from avp_cli.agents import ResolvedAgent
    from avp_cli.eval.engine import RunObserver

    agent_script = tmp_path / "tiny_agent.py"
    agent_script.write_text(_INLINE_AGENT)
    agent = ResolvedAgent(
        name="scripted",
        manifest=AgentManifest(command=[sys.executable, str(agent_script)]),
        manifest_cwd=tmp_path,
    )
    ev = Eval(
        setups=[_setup("solo")],
        dataset=Dataset(name="d", items=[Item(id="i1", prompt="x", expected="all done")]),
        scorer=ExactMatchScorer(),
    )

    starts: list[tuple] = []
    seen_types: list[str] = []
    ends: list = []
    observer = RunObserver(
        on_start=lambda n, t, agent, s, i: starts.append((n, t, agent, s, i)),
        on_event=lambda ev: seen_types.append(getattr(ev, "type", "?")),
        on_end=lambda n, t, agent, r: ends.append((agent, r)),
    )

    board = run_eval(ev, agent=agent, out_dir=tmp_path / "runs", observer=observer)

    assert starts == [(1, 1, "scripted", "solo", "i1")]
    # the scripted agent emits a model turn + a tool round-trip + agent_stopped
    assert "avp.assistant_message" in seen_types
    assert "avp.tool_invoked" in seen_types
    assert "avp.agent_stopped" in seen_types
    assert len(ends) == 1 and ends[0][0] == "scripted" and ends[0][1].passed
    assert board.rows[0].accuracy == 1.0  # scoring still works alongside streaming


def test_tool_tally_is_busiest_first_and_compact() -> None:
    from avp_cli.observability import ToolUsage, tool_tally

    s = Summary(run_id="r")
    s.tools = {
        "Read": ToolUsage(name="Read", invocations=2),
        "Bash": ToolUsage(name="Bash", invocations=4),
    }
    assert tool_tally(s) == "Bash:4 Read:2"
    assert tool_tally(Summary(run_id="r")) == ""  # no tools


def test_run_matrix_interleaves_agents_and_compares(tmp_path) -> None:
    """Two agents over one task: task-major order (both agents per item) and an
    on_compare callback fires once per task with both results."""
    from avp_conformance.manifest import AgentManifest

    from avp_cli.agents import ResolvedAgent
    from avp_cli.eval.engine import RunObserver, run_matrix

    agent_script = tmp_path / "tiny_agent.py"
    agent_script.write_text(_INLINE_AGENT)

    def mk(name: str) -> ResolvedAgent:
        return ResolvedAgent(
            name=name,
            manifest=AgentManifest(command=[sys.executable, str(agent_script)]),
            manifest_cwd=tmp_path,
        )

    agents = [mk("alpha"), mk("beta")]
    ev = Eval(
        setups=[_setup("solo")],
        dataset=Dataset(name="d", items=[Item(id="i1", prompt="x", expected="all done")]),
        scorer=ExactMatchScorer(),
    )

    start_agents: list[str] = []
    compares: list[tuple] = []
    observer = RunObserver(
        on_start=lambda n, t, agent, s, i: start_agents.append(agent),
        on_compare=lambda s, i, pairs: compares.append((s, i, [a for a, _ in pairs])),
    )

    boards = run_matrix(ev, agents, out_dir=tmp_path / "runs", observer=observer, compare=True)

    # task-major: both agents run on the one item, back-to-back
    assert start_agents == ["alpha", "beta"]
    # one head-to-head per task, carrying both agents' results
    assert compares == [("solo", "i1", ["alpha", "beta"])]
    # one board per agent, each scored
    assert [b.agent_label for b in boards] == ["alpha", "beta"]
    assert all(b.rows[0].accuracy == 1.0 for b in boards)


def test_run_matrix_binds_commissions_to_their_agent(tmp_path) -> None:
    """Seam: a commission bound to one agent (the `{agent: [ids]}` map form) runs
    only on that agent; an unbound one still runs on every agent. Each board
    carries only its agent's commissions, and no head-to-head fires for a
    commission that ran on a single agent."""
    from avp_conformance.manifest import AgentManifest

    from avp_cli.agents import ResolvedAgent
    from avp_cli.eval.engine import RunObserver, run_matrix

    agent_script = tmp_path / "tiny_agent.py"
    agent_script.write_text(_INLINE_AGENT)

    def mk(name: str) -> ResolvedAgent:
        return ResolvedAgent(
            name=name,
            manifest=AgentManifest(command=[sys.executable, str(agent_script)]),
            manifest_cwd=tmp_path,
        )

    def bound(id_: str, agent: str | None) -> Setup:
        return Setup(id=id_, commission=Commission(schema_version="0.1", run_id=id_), agent=agent)

    agents = [mk("goose"), mk("claude-code")]
    ev = Eval(
        setups=[
            bound("for-goose", "goose"),
            bound("for-claude", "claude-code"),
            bound("shared", None),
        ],
        dataset=Dataset(name="d", items=[Item(id="i1", prompt="x", expected="all done")]),
        scorer=ExactMatchScorer(),
    )

    started: list[tuple[str, str]] = []
    compares: list[str] = []
    observer = RunObserver(
        on_start=lambda n, t, agent, s, i: started.append((agent, s)),
        on_compare=lambda s, i, pairs: compares.append(s),
    )
    boards = run_matrix(ev, agents, out_dir=tmp_path / "runs", observer=observer, compare=True)

    # bound commissions ran only on their agent; the unbound one ran on both
    assert ("goose", "for-goose") in started
    assert ("claude-code", "for-claude") in started
    assert ("claude-code", "for-goose") not in started
    assert ("goose", "for-claude") not in started
    assert ("goose", "shared") in started and ("claude-code", "shared") in started
    # 1 (goose-only) + 1 (claude-only) + 2 (shared on both) = 4 runs total
    assert len(started) == 4
    # only the shared commission ran on >1 agent, so only it gets a head-to-head
    assert compares == ["shared"]
    # each board shows only its own agent's commissions
    by_agent = {b.agent_label: {r.name for r in b.rows} for b in boards}
    assert by_agent["goose"] == {"for-goose", "shared"}
    assert by_agent["claude-code"] == {"for-claude", "shared"}
