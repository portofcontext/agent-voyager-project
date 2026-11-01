"""Grade saved child artifacts, independently of the outer agent's DONE claim.

This is a cooperative onboarding task, not a tamper-resistant benchmark. An
agent could forge artifacts; inspect suspicious traces before drawing conclusions.
"""

from __future__ import annotations

import json
from pathlib import Path

from build_commissions import CASES, sha256

from avp.commission import Commission
from avp_cli import config as eval_config
from avp_cli.agent import _WORKSPACE_MNT, read_trajectory
from avp_cli.eval.engine import Eval, _resume_cell, extract_final_output
from avp_cli.eval.setup import Setup
from avp_cli.observability import summarize


def saved_path(workspace: Path, value: str) -> Path:
    path = Path(value)
    if path.is_relative_to(_WORKSPACE_MNT):
        path = workspace / path.relative_to(_WORKSPACE_MNT)
    elif not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    if not path.is_relative_to(workspace.resolve()):
        raise ValueError("artifact must be in the saved workspace")
    return path


def normalized_rows(workspace: Path, rows: list[dict]) -> list[dict]:
    rows = json.loads(json.dumps(rows))
    for row in rows:
        for run in row["runs"]:
            run["trajectory_path"] = str(saved_path(workspace, run["trajectory_path"]))
        row["runs"].sort(key=lambda run: run["item_id"])
    return sorted(rows, key=lambda row: row["name"])


def verify(workspace: Path, plan: dict, expected_model: str | None = None) -> dict:
    checks = {}
    errors = []
    cost = 0.0
    seen = set()
    for path in workspace.rglob("*.ndjson"):
        try:
            for event in read_trajectory(path):
                if event.type == "avp.assistant_message" and event.id not in seen:
                    cost += event.data.cost_usd
                    seen.add(event.id)
        except (OSError, ValueError, AttributeError):
            continue
    try:
        checks["inputs_unchanged"] = all(
            sha256(workspace / "inputs" / name) == digest
            for name, digest in plan["inputs"].items()
            if name != "avp.skill"
        )
        board = json.loads((workspace / "child-board.json").read_text())
        resumed = json.loads((workspace / "resumed-board.json").read_text())
        if isinstance(board, list):
            board = board[0]
        if isinstance(resumed, list):
            resumed = resumed[0]
        output_dir = saved_path(workspace, board["trajectories_dir"])
        manifest_path = output_dir / "run.json"
        manifest = json.loads(manifest_path.read_text())

        def delivered(path: Path) -> bool:
            # The task permits saving a copy of the run beneath child-output.
            # Require identical bytes, not just a matching filename.
            return any(
                sha256(candidate) == sha256(path)
                for candidate in (workspace / "child-output").rglob(path.name)
                if candidate.is_file()
            )

        # Resume rewrites created_at. A pre-resume manifest copy remains valid
        # when every configuration and provenance field is identical.
        manifest_body = {k: v for k, v in manifest.items() if k != "created_at"}
        artifacts_saved = any(
            {k: v for k, v in json.loads(candidate.read_text()).items() if k != "created_at"}
            == manifest_body
            for candidate in (workspace / "child-output").rglob("run.json")
        )
        config = manifest["eval_config"]
        checks["local_child_runtime"] = manifest["run"]["runtime"] == "local"
        spec = dict(config["dataset"])
        checks["file_dataset"] = spec["source"] == "file"
        if not checks["file_dataset"]:
            raise ValueError("expected a file dataset")
        spec["path"] = str(saved_path(workspace, spec["path"]))
        dataset = eval_config._build_dataset(spec, name="onboarding")

        def signature(prompt, expected):
            return json.dumps([prompt, expected], sort_keys=True)

        checks["supplied_cases"] = sorted(
            signature(item.prompt, item.expected) for item in dataset
        ) == sorted(signature(case["question"], case["expected"]) for case in CASES)
        checks["scorer"] = (
            config["scorer"]["name"] == "structural-match"
            and config["scorer"].get("threshold", 1) == 1
        )
        commissions = manifest["commissions"]
        checks["two_variants"] = len(commissions) == 2
        bodies = [Commission.model_validate(v["commission"]) for v in commissions.values()]
        setups = {name: Setup(name, body) for name, body in zip(commissions, bodies, strict=True)}
        replay = Eval(
            setups=list(setups.values()),
            dataset=dataset,
            scorer=eval_config._build_scorer(config["scorer"]),
        )
        checks["requested_model"] = expected_model is None or all(
            c.model == expected_model for c in bodies
        )
        checks["distinct_instructions"] = len({(c.prompt, c.system_prompt) for c in bodies}) == 2
        checks["structured_output"] = all(
            c.output_schema
            and "answer" in c.output_schema.get("required", [])
            and c.output_schema.get("properties", {}).get("answer", {}).get("type") == "integer"
            and "{input}" in (c.prompt or "")
            for c in bodies
        )
        checks["released_adapter"] = any(
            s.get("from") == "release" and s.get("agent") == "pydantic-ai"
            for s in manifest["run"]["agent_sources"]
        )
        rows = board["commissions"]
        checks["board"] = len(rows) == 2 and all(
            r["n_items"] == len(CASES) and r["n_errors"] == 0 and r["pass_rate"] == 1 for r in rows
        )
        checks["resume_same_results"] = normalized_rows(workspace, rows) == normalized_rows(
            workspace, resumed["commissions"]
        )
        expected = {item.id: item.expected for item in dataset}
        items = {item.id: item for item in dataset}
        traced = set()
        trace_paths = set()
        trace_ok = True
        resumable = True
        for row in rows:
            for run in row["runs"]:
                path = saved_path(workspace, run["trajectory_path"])
                artifacts_saved &= delivered(path)
                trace_paths.add(path)
                events = read_trajectory(path)
                summary = summarize(events)
                start = next(e for e in events if e.type == "avp.run_requested")
                stop = events[-1]
                traced.add((row["name"], run["item_id"]))
                item = items[run["item_id"]]
                setup = setups[row["name"]]
                reused = _resume_cell(path, replay, setup, item)
                resumable &= reused is not None and reused.score.passed
                trace_ok &= (
                    extract_final_output(events).structured == expected.get(run["item_id"])
                    and summary.total_turns > 0
                    and not summary.errors
                    and stop.type == "avp.agent_stopped"
                    and str(stop.data.reason) == "converged"
                    and start.data.commission.model in {c.model for c in bodies}
                    and start.data.commission.prompt == setup.render_prompt(item)
                    and start.data.commission.system_prompt == setup.commission.system_prompt
                )
        checks["six_successful_traces"] = (
            trace_ok
            and traced == {(v, c) for v in commissions for c in expected}
            and len(trace_paths) == len(commissions) * len(CASES)
        )
        checks["resume_reuses_saved_traces"] = resumable and checks["six_successful_traces"]
        checks["artifacts_saved"] = artifacts_saved
        checks["report"] = bool((workspace / "report.md").read_text().strip())
        checks["reproducible_config"] = (
            json.loads((workspace / "comparison.eval.json").read_text()) == config
        )
    except (OSError, ValueError, KeyError, TypeError, StopIteration, AttributeError) as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return {
        "passed": bool(checks) and all(checks.values()) and not errors,
        "evaluation_completed": all(
            checks.get(k, False)
            for k in (
                "local_child_runtime",
                "two_variants",
                "supplied_cases",
                "distinct_instructions",
                "structured_output",
                "released_adapter",
                "requested_model",
                "board",
                "six_successful_traces",
                "resume_same_results",
                "resume_reuses_saved_traces",
            )
        ),
        "checks": checks,
        "errors": errors,
        "child_cost_usd": cost,
    }
