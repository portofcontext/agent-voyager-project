"""avp_cli — the local AVP CLI (`avp`): build, run, and iterate on Commissions.

An eval is a JSON config file (no user code); the CLI is the engine. It loads a
config, composes a Commission per setup, runs each against a real agent (Goose /
Claude Code) via the agent's `run --commission --out` manifest contract, scores
each run, and ranks a board by accuracy / pass-rate / cost / turns.
"""

from __future__ import annotations

from avp_cli.agent import load_manifest, run_agent
from avp_cli.agents import ResolvedAgent, known_agents, preflight, resolve_agent
from avp_cli.config import EvalConfigError, eval_from_dict, load_eval
from avp_cli.eval.dataset import Dataset, Item
from avp_cli.eval.engine import (
    Board,
    Eval,
    RunObserver,
    RunResult,
    SetupRow,
    extract_final_output,
    run_eval,
    run_matrix,
)
from avp_cli.eval.report import (
    board_table,
    board_to_dict,
    comparison_table,
    dump_json,
    failures,
)
from avp_cli.eval.scoring import (
    ExactMatchScorer,
    FidelityScorer,
    FinalOutput,
    Score,
    Scorer,
    StructuralMatchScorer,
)
from avp_cli.eval.setup import Setup
from avp_cli.observability import Summary, ToolUsage, render, summarize, tool_tally

__all__ = [
    "Board",
    "Dataset",
    "Eval",
    "EvalConfigError",
    "ExactMatchScorer",
    "FidelityScorer",
    "FinalOutput",
    "Item",
    "ResolvedAgent",
    "RunObserver",
    "RunResult",
    "Score",
    "Scorer",
    "Setup",
    "SetupRow",
    "StructuralMatchScorer",
    "Summary",
    "ToolUsage",
    "board_table",
    "board_to_dict",
    "comparison_table",
    "dump_json",
    "eval_from_dict",
    "extract_final_output",
    "failures",
    "known_agents",
    "load_eval",
    "load_manifest",
    "preflight",
    "render",
    "resolve_agent",
    "run_agent",
    "run_eval",
    "run_matrix",
    "summarize",
    "tool_tally",
]
