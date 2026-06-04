"""The eval loop: run every setup over every item, score it, aggregate a board.

`run_eval` is `len(setups) * len(items)` real agent runs. Each run drives a real
AVP agent (Goose or Claude Code) through its manifest contract
(`agent.run_agent`) and reduces the trajectory with `observability.summarize`.
The only new trajectory reading is `extract_final_output`, which pulls the
agent's final answer from `agent_stopped.output`, falling back to the last
`assistant_message` text.

A failed run (subprocess crash, unparseable stream) is captured per-cell rather
than aborting the whole matrix, so one bad run never sinks a paid board.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from avp.content import TextBlock
from avp.trajectory import AgentStoppedEvent, AssistantMessageEvent, ToolInvokedEvent
from avp_cli.agent import SandboxContext, SandboxedAgent, read_trajectory, run_agent
from avp_cli.eval.dataset import Dataset, Item
from avp_cli.eval.scoring import FinalOutput, Score, Scorer
from avp_cli.eval.setup import Setup
from avp_cli.observability import Summary, summarize


@dataclass(frozen=True)
class Eval:
    """A complete eval definition: what to run, over what, scored how.

    `setups` are the commissions to compare (resolved from the library by id).
    Each commission carries its own model; there is no eval-level default.
    """

    setups: list[Setup]
    dataset: Dataset
    scorer: Scorer
    # Agents the eval runs against by default (registry names or manifest paths).
    # `avp init` picks these; `--agent` at run time overrides. Empty -> the CLI's
    # DEFAULT_AGENT.
    agents: list[str] = field(default_factory=list)


def setups_for(setups: list[Setup], agent_name: str) -> list[Setup]:
    """The setups that run on `agent_name`: unbound (`agent is None`) plus those
    bound to it. A bound setup is invisible to every other agent, so this is the
    single source of truth for the matrix, its progress total, and per-agent
    board / payload assembly."""
    return [s for s in setups if s.agent is None or s.agent == agent_name]


# ── Final-answer extraction ────────────────────────────────────────────────


# The Claude Agent SDK routes structured output (a Commission `output_schema`)
# through a tool call by this name; its input IS the structured answer. Other
# agents inline the JSON in the final message instead. extract_final_output
# handles both so the eval reads the answer wherever the agent put it.
_STRUCTURED_OUTPUT_TOOL = "StructuredOutput"


def _loads_dict(s: str) -> dict[str, Any] | None:
    try:
        v = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def _coerce_json(text: str | None) -> dict[str, Any] | None:
    """Best-effort: find a JSON object in `text` (whole, fenced, or embedded)."""
    if not text:
        return None
    candidate = text.strip()
    obj = _loads_dict(candidate)
    if obj is not None:
        return obj
    if "```" in candidate:
        # fenced blocks sit at odd indices when splitting on the fence marker
        parts = candidate.split("```")
        for block in parts[1::2]:
            block = block[4:] if block.lower().startswith("json") else block
            obj = _loads_dict(block.strip())
            if obj is not None:
                return obj
    i, j = candidate.find("{"), candidate.rfind("}")
    if 0 <= i < j:
        return _loads_dict(candidate[i : j + 1])
    return None


def extract_final_output(events: list[BaseModel | dict[str, Any]]) -> FinalOutput:
    """Pull the agent's final answer from the trajectory.

    Precedence: `agent_stopped.output` (the agent's declared result), then a
    structured-output tool call's input, then the last non-empty
    `assistant_message` text (whole / fenced / embedded JSON). A dict from any
    source is the structured answer; text is JSON-parsed as a fallback.
    """
    stop_output: Any = None
    stop_reason: str | None = None
    last_assistant_text: str | None = None
    structured_tool_input: dict[str, Any] | None = None

    for ev in events:
        if isinstance(ev, AgentStoppedEvent):
            stop_output = ev.data.output
            stop_reason = str(ev.data.reason)
        elif isinstance(ev, AssistantMessageEvent):
            texts = [b.text for b in ev.data.content if isinstance(b, TextBlock) and b.text.strip()]
            if texts:
                last_assistant_text = "\n".join(texts)
        elif isinstance(ev, ToolInvokedEvent) and ev.data.tool_name == _STRUCTURED_OUTPUT_TOOL:
            if isinstance(ev.data.tool_input, dict):
                structured_tool_input = ev.data.tool_input

    text: str | None = None
    structured: dict[str, Any] | None = None
    if isinstance(stop_output, dict):
        structured = stop_output
        text = json.dumps(stop_output)
    elif isinstance(stop_output, str) and stop_output.strip():
        text = stop_output
    if structured is None and structured_tool_input is not None:
        structured = structured_tool_input
        if text is None:
            text = json.dumps(structured_tool_input)
    if text is None:
        text = last_assistant_text
    if structured is None:
        structured = _coerce_json(text)
    return FinalOutput(text=text, structured=structured, stop_reason=stop_reason)


# ── Per-run + aggregate results ────────────────────────────────────────────


@dataclass
class RunResult:
    setup_name: str
    item_id: str
    score: Score | None = None
    summary: Summary | None = None
    output: FinalOutput | None = None
    trajectory_path: str | None = None
    spawn_error: str | None = None

    @property
    def value(self) -> float:
        return self.score.value if self.score else 0.0

    @property
    def passed(self) -> bool:
        return bool(self.score and self.score.passed)


@dataclass
class SetupRow:
    name: str
    description: str
    model: str | None
    n_items: int
    n_errors: int
    accuracy: float
    pass_rate: float
    cost_per_run: float
    turns_per_run: float
    total_cost: float
    results: list[RunResult] = field(default_factory=list)


@dataclass
class Board:
    dataset_name: str
    agent_label: str
    out_dir: str
    rows: list[SetupRow]
    interrupted: bool = False  # True if the run was stopped early (Ctrl-C)

    @property
    def total_runs(self) -> int:
        return sum(r.n_items for r in self.rows)

    @property
    def total_cost(self) -> float:
        return sum(r.total_cost for r in self.rows)


@dataclass
class RunObserver:
    """Optional hooks for live progress. All calls run on the main thread.

    `on_start(n, total, agent, setup, item)` fires before each run;
    `on_event(event)` fires per trajectory event while that run streams;
    `on_end(n, total, agent, result)` fires once the run is scored;
    `on_compare(setup, item, pairs)` fires after every agent has run one task
    (interleaved multi-agent mode only), with `pairs = [(agent, result), ...]`.
    """

    on_start: Callable[[int, int, str, str, str], None] | None = None
    on_event: Callable[[Any], None] | None = None
    on_end: Callable[[int, int, str, RunResult], None] | None = None
    on_compare: Callable[[str, str, list[tuple[str, RunResult]]], None] | None = None


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _execute(
    ev: Eval,
    agent: SandboxedAgent,
    sandbox_ctx: SandboxContext,
    setup: Setup,
    item: Item,
    *,
    out: Path,
    model_override: str | None,
    timeout_s: float,
    on_event: Callable[[Any], None] | None,
) -> RunResult:
    """Run one (agent, commission, item) cell and score it into a RunResult."""
    run_id = f"{agent.name}-{setup.id}-{item.id}"
    commission = setup.to_commission(item, run_id, model_override=model_override)
    traj_path = out / f"{run_id}.ndjson"
    events, err = run_agent(
        agent,
        sandbox_ctx,
        commission,
        out_path=traj_path,
        timeout_s=timeout_s,
        on_event=on_event,
    )
    if err is not None or events is None:
        return RunResult(setup.id, item.id, spawn_error=err or "no events")
    summary = summarize(events)
    output = extract_final_output(events)
    return RunResult(
        setup_name=setup.id,
        item_id=item.id,
        score=ev.scorer.score(item, output, summary),
        summary=summary,
        output=output,
        trajectory_path=str(traj_path),
    )


def _resume_cell(traj_path: Path, ev: Eval, setup: Setup, item: Item) -> RunResult | None:
    """Reuse a previously completed cell instead of re-running the agent.

    A cell counts as done only if its trajectory file exists and ends in a
    terminal `agent_stopped` event; a file truncated by a kill / crash / sleep
    has no terminal event, so we return None and the caller re-runs it. The agent
    run (the paid, slow part) is skipped; the cell is still re-scored from its
    saved events (the scorer may call a grader model). Returns None on any read
    error so a corrupt file just re-runs.
    """
    if not traj_path.is_file():
        return None
    try:
        events = read_trajectory(traj_path)
    except (OSError, ValueError):
        return None
    if not any(isinstance(e, AgentStoppedEvent) for e in events):
        return None  # partial / killed mid-run -> re-run the whole cell
    summary = summarize(events)
    output = extract_final_output(events)
    return RunResult(
        setup_name=setup.id,
        item_id=item.id,
        score=ev.scorer.score(item, output, summary),
        summary=summary,
        output=output,
        trajectory_path=str(traj_path),
    )


def run_matrix(
    ev: Eval,
    agents: list[SandboxedAgent],
    sandbox_ctx: SandboxContext,
    *,
    out_dir: str | Path,
    max_items: int | None = None,
    model: str | None = None,
    timeout_s: float = 300.0,
    observer: RunObserver | None = None,
    compare: bool = False,
    resume: bool = False,
) -> list[Board]:
    """Run every (setup, item) against every agent and return one Board per agent.

    The loop is task-major: for each item, every agent runs back-to-back (so the
    observer can show a head-to-head the moment they all finish). `compare`
    enables the per-task `on_compare` callback. Ctrl-C stops the matrix and
    returns Boards of whatever finished, each `interrupted=True`.

    With `resume`, a cell whose trajectory file is already complete (ends in a
    terminal `agent_stopped`) is reused instead of re-run; partial / missing cells
    run normally. Reused cells are re-scored from their saved events.
    """
    obs = observer or RunObserver()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items = list(ev.dataset.items)[:max_items] if max_items else list(ev.dataset.items)
    total = len(items) * sum(len(setups_for(ev.setups, a.name)) for a in agents)
    n = 0

    # acc[agent.name][commission.id] -> list[RunResult]
    acc: dict[str, dict[str, list[RunResult]]] = {
        a.name: {s.id: [] for s in ev.setups} for a in agents
    }
    interrupted = False
    try:
        for setup in ev.setups:
            for item in items:
                pairs: list[tuple[str, RunResult]] = []
                for agent in agents:
                    if setup.agent is not None and setup.agent != agent.name:
                        continue  # commission bound to a different agent
                    n += 1
                    if obs.on_start:
                        obs.on_start(n, total, agent.name, setup.id, item.id)
                    run_id = f"{agent.name}-{setup.id}-{item.id}"
                    result = None
                    if resume:
                        result = _resume_cell(out / f"{run_id}.ndjson", ev, setup, item)
                    if result is None:
                        result = _execute(
                            ev,
                            agent,
                            sandbox_ctx,
                            setup,
                            item,
                            out=out,
                            model_override=model,
                            timeout_s=timeout_s,
                            on_event=obs.on_event,
                        )
                    acc[agent.name][setup.id].append(result)
                    if obs.on_end:
                        obs.on_end(n, total, agent.name, result)
                    pairs.append((agent.name, result))
                # Head-to-head only when this commission actually ran on >1 agent.
                if compare and obs.on_compare and len(pairs) > 1:
                    obs.on_compare(setup.id, item.id, pairs)
    except KeyboardInterrupt:
        interrupted = True

    boards: list[Board] = []
    for agent in agents:
        rows = [
            _aggregate(s, acc[agent.name][s.id])
            for s in setups_for(ev.setups, agent.name)
            if acc[agent.name][s.id]
        ]
        boards.append(
            Board(
                dataset_name=ev.dataset.name,
                agent_label=agent.name,
                out_dir=str(out),
                rows=rank_rows(rows),
                interrupted=interrupted,
            )
        )
    return boards


def run_eval(
    ev: Eval,
    *,
    agent: SandboxedAgent,
    sandbox_ctx: SandboxContext,
    out_dir: str | Path,
    max_items: int | None = None,
    model: str | None = None,
    timeout_s: float = 300.0,
    observer: RunObserver | None = None,
    resume: bool = False,
) -> Board:
    """Run the matrix against a single `agent` and return its ranked `Board`.

    Thin wrapper over `run_matrix` for the one-agent case (and tests).
    """
    return run_matrix(
        ev,
        [agent],
        sandbox_ctx,
        out_dir=out_dir,
        max_items=max_items,
        model=model,
        timeout_s=timeout_s,
        observer=observer,
        compare=False,
        resume=resume,
    )[0]


def rank_rows(rows: list[SetupRow]) -> list[SetupRow]:
    """Rank setups by accuracy desc, then pass_rate desc, then cheapest first."""
    return sorted(rows, key=lambda r: (-r.accuracy, -r.pass_rate, r.cost_per_run))


def _aggregate(setup: Setup, results: list[RunResult]) -> SetupRow:
    ran = [r for r in results if r.summary is not None]
    return SetupRow(
        name=setup.id,
        description="",  # commissions carry no non-wire description; the diff is the config
        model=setup.model,
        n_items=len(results),
        n_errors=sum(1 for r in results if r.spawn_error is not None),
        # accuracy / pass_rate span every item; a crashed run scores 0 / not passed.
        accuracy=_mean([r.value for r in results]),
        pass_rate=_mean([1.0 if r.passed else 0.0 for r in results]),
        # cost / turns average only over runs that actually produced a trajectory.
        cost_per_run=_mean([r.summary.total_cost_usd for r in ran]),
        turns_per_run=_mean([float(r.summary.total_turns) for r in ran]),
        total_cost=sum(r.summary.total_cost_usd for r in ran),
        results=results,
    )
