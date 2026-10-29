"""Prepared trials load as real evals; saved CLI artifacts drive the grader."""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from avp.commission import Commission
from avp_cli import cli, config, library

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/onboarding"


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLE))
    return importlib.import_module("build_commissions"), importlib.import_module("verify")


def test_generated_trials_load_and_only_onboarding_material_varies(experiment, tmp_path):
    build, _ = experiment
    wheel = tmp_path / "avp_cli-0.4.0-py3-none-any.whl"
    wheel.write_bytes(b"test-only wheel fixture")
    out = tmp_path / "batch"
    plan = build.prepare(out, wheel, repetitions=1, agents={"codex": "codex-local"})
    assert len(plan["trials"]) == len(build.MODELS) * len(build.STRATEGIES)
    for agent in build.MODELS:
        bases = []
        tasks = []
        for trial in (t for t in plan["trials"] if t["agent"] == agent):
            cfg = json.loads((out / "evals" / f"{trial['id']}.json").read_text())
            assert cfg["agents"] == [plan["agent_locators"][agent]]
            ev = config.eval_from_dict(cfg, commissions_dir=out / "commissions")
            tasks.append(ev.dataset.items[0].prompt)
            body = ev.setups[0].commission.model_dump(exclude_none=True)
            for field in ("run_id", "skills", "system_prompt"):
                body.pop(field, None)
            bases.append(body)
        assert all(b == bases[0] for b in bases)
        assert len(set(tasks)) == 1
    env = json.loads((out / "environment.json").read_text())
    assert all("install" not in step for step in env.get("setup", []))
    assert set(build.MODELS) == {"codex", "claude-code", "pi"}
    assert plan["agent_locators"]["codex"] == "codex-local"
    assert all(
        not json.loads(p.read_text()).get("mcp_servers")
        for p in (out / "commissions").glob("*.json")
    )
    assert "inputs/avp.skill" not in env["files"]  # no skill leaked into the control
    skill_cm = next((out / "commissions").glob("*-claude-code-skill.json"))
    skill = json.loads(skill_cm.read_text())["skills"][0]["files"]
    assert "SKILL.md" in skill and "avp/core/spec/v0.1/commission.md" in skill


SCRIPT = """
import json
from avp.agent_cli import main
from avp.content import TextBlock
from avp.descriptor import AgentDescriptor
from avp.recorder import Recorder
from avp.trajectory import StopReason, Usage

def describe():
    return AgentDescriptor(agent_name="fixture", agent_version="0.0.0", spec_version="0.1")

async def run(cm, sink):
    rec = Recorder(sink, run_id=cm.run_id, provider="test")
    await rec.prelude(cm, describe())
    await rec.start(request_model=cm.model, prompt=cm.prompt)
    answer = 42 if "17 + 25" in cm.prompt else 63 if "9 times 7" in cm.prompt else 72
    output = {"answer": answer}
    await rec.assistant([TextBlock(text=json.dumps(output))], Usage(input_tokens=1, output_tokens=1), model=cm.model)
    await rec.stop(StopReason.converged, output)

raise SystemExit(main(run=run, describe=describe, prog="fixture"))
"""


@pytest.mark.parametrize(
    "names, converted", [(("direct", "careful"), False), (("brief", "reasoned"), True)]
)
def test_grader_checks_real_cli_outputs_and_rejects_bad_evidence(
    experiment, tmp_path, monkeypatch, names, converted
):
    build, grader = experiment
    monkeypatch.setenv("AVP_HOME", str(tmp_path / "child-home"))
    monkeypatch.chdir(tmp_path)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    cases = inputs / "cases.jsonl"
    cases.write_text("".join(json.dumps(c) + "\n" for c in build.CASES))
    plan = {"inputs": {"cases.jsonl": build.sha256(cases)}}
    (tmp_path / "fixture.py").write_text(SCRIPT)
    manifest = tmp_path / "fixture.json"
    build.write_json(manifest, {"command": [sys.executable, str(tmp_path / "fixture.py")]})
    for name in names:
        library.save(
            name,
            Commission(
                schema_version="0.1",
                run_id=name,
                model="test/model",
                prompt="{input}",
                system_prompt=name,
                output_schema={
                    "type": "object",
                    "required": ["answer"],
                    "properties": {"answer": {"type": "integer"}},
                },
            ),
        )
    eval_path = tmp_path / "comparison.eval.json"
    build.write_json(
        eval_path,
        {
            "agents": [str(manifest)],
            "commissions": list(names),
            "dataset": {
                "source": "file",
                "path": str(cases),
                "input": "{question}",
                "expected_field": "expected",
                "id_field": "id",
            },
            "scorer": {"name": "structural-match", "threshold": 1.0},
        },
    )
    if converted:
        converted_cases = tmp_path / "converted.jsonl"
        converted_cases.write_text(
            "".join(
                json.dumps({"key": str(i), "prompt": c["question"], "expected": c["expected"]})
                + "\n"
                for i, c in enumerate(build.CASES)
            )
        )
        cfg = json.loads(eval_path.read_text())
        cfg["dataset"].update(path=str(converted_cases), input="{prompt}", id_field="key")
        build.write_json(eval_path, cfg)
    out = tmp_path / "child-output"
    if converted:
        out /= "comparison-run"
    argv = ["eval", "run", str(eval_path), "--runtime", "local", "--out", str(out), "--quiet"]
    assert cli.main([*argv, "--name", "child", "--json", str(tmp_path / "child-board.json")]) == 0
    hashes = {p.name: build.sha256(p) for p in out.glob("*.ndjson")}
    assert (
        cli.main([*argv, "--resume", "child", "--json", str(tmp_path / "resumed-board.json")]) == 0
    )
    assert hashes == {p.name: build.sha256(p) for p in out.glob("*.ndjson")}
    (tmp_path / "report.md").write_text("Reproducible report fixture. " * 10)
    result = grader.verify(tmp_path, plan)
    assert not result["passed"]  # custom scripted adapter is not a released model adapter
    assert result["errors"] == []
    assert not result["checks"].pop("released_adapter")
    assert all(result["checks"].values()), result
    # Only the provenance gate is simulated here, after exercising real CLI output.
    saved = json.loads((out / "run.json").read_text())
    saved["run"]["agent_sources"] = [{"from": "release", "agent": "pydantic-ai"}]
    build.write_json(out / "run.json", saved)
    assert grader.verify(tmp_path, plan)["passed"]
    # AVP may run in its default home, with a byte-identical copy delivered
    # beneath child-output. The board still names the original run paths.
    if converted:
        original_run = tmp_path / "child-home/runs/default-run"
        shutil.copytree(out, original_run)
        resumed_manifest = json.loads((original_run / "run.json").read_text())
        resumed_manifest["created_at"] = "2026-10-22T00:00:00Z"
        build.write_json(original_run / "run.json", resumed_manifest)
        for board_path in (tmp_path / "child-board.json", tmp_path / "resumed-board.json"):
            board = json.loads(board_path.read_text())
            entries = board if isinstance(board, list) else [board]
            for entry in entries:
                entry["trajectories_dir"] = str(original_run)
                for row in entry["commissions"]:
                    for run in row["runs"]:
                        run["trajectory_path"] = str(
                            original_run / Path(run["trajectory_path"]).name
                        )
            build.write_json(board_path, board)
        assert grader.verify(tmp_path, plan)["passed"]
    resumed_path = tmp_path / "resumed-board.json"
    resumed = json.loads(resumed_path.read_text())
    rows = resumed[0]["commissions"] if isinstance(resumed, list) else resumed["commissions"]
    run = rows[0]["runs"][0]
    original_trace = run["trajectory_path"]
    run["trajectory_path"] = "/avp/workspace/" + str(Path(original_trace).relative_to(tmp_path))
    build.write_json(resumed_path, resumed)
    assert grader.verify(tmp_path, plan)["passed"]
    run["trajectory_path"] = "/avp/workspace/child-output/different.ndjson"
    build.write_json(resumed_path, resumed)
    assert not grader.verify(tmp_path, plan)["checks"]["resume_same_results"]
    run["trajectory_path"] = original_trace
    score = run["score"]["value"]
    run["score"]["value"] = 0
    build.write_json(resumed_path, resumed)
    assert not grader.verify(tmp_path, plan)["checks"]["resume_same_results"]
    run["score"]["value"] = score
    build.write_json(resumed_path, resumed)
    # Correct-looking boards must not hide a different input dataset.
    dataset_path = Path(saved["eval_config"]["dataset"]["path"])
    original = dataset_path.read_text()
    dataset_path.write_text(original.replace("17 + 25", "17 + 26"))
    assert not grader.verify(tmp_path, plan)["passed"]
    dataset_path.write_text(original)
    next(out.glob("*.ndjson")).write_text("malformed\n")
    assert not grader.verify(tmp_path, plan)["passed"]
    assert grader.verify(tmp_path / "missing", plan)["passed"] is False
