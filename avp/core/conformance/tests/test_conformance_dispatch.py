"""Seam test: `avp-conformance check` ↔ agent subprocess.

Crosses the harness↔agent seam without a real model. A stub agent script
honors the agent CLI contract (`ping`, `run --commission --out`) by writing
a canned NDJSON trajectory; the harness writes the Commission to a temp file,
spawns the stub, reads the trajectory back, and matches it. This pins the
parts a matcher unit test can't see: argument plumbing, file round-trip,
exit-code semantics, and PASS/FAIL reporting.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from avp_conformance._app import app
from typer.testing import CliRunner

runner = CliRunner()

# A stub agent: `ping` writes pong; `run` writes a fixed converged trajectory,
# ignoring the Commission contents (this test exercises plumbing, not a model).
STUB_AGENT = """\
import argparse, json, sys

TRAJECTORY = [
    {"type": "avp.run_requested", "source": "avp://agent", "data": {}},
    {"type": "avp.agent_described", "source": "avp://agent", "data": {}},
    {"type": "avp.agent_started", "source": "avp://agent", "data": {}},
    {"type": "avp.agent_stopped", "source": "avp://agent", "data": {"avp.reason": "converged"}},
]

p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd", required=True)
pp = sub.add_parser("ping"); pp.add_argument("--out", required=True)
pr = sub.add_parser("run")
pr.add_argument("--commission", required=True)
pr.add_argument("--built-in", dest="built_in", required=False)
pr.add_argument("--out", required=True)
a = p.parse_args()
with open(a.out, "w") as f:
    if a.cmd == "ping":
        f.write(json.dumps({"type": "pong"}) + "\\n")
    else:
        for ev in TRAJECTORY:
            f.write(json.dumps(ev) + "\\n")
"""

PASSING_CASE = {
    "id": "stub-converges",
    "title": "stub agent reaches converged",
    "commission": {"schema_version": "0.1", "run_id": "stub-converges", "model": "stub/mock"},
    "expectations": {
        "ordering": "in_order_subsequence",
        "events": [
            {"match": {"type": "avp.run_requested", "source": "avp://agent"}},
            {"match": {"type": "avp.agent_stopped", "data": {"avp.reason": "converged"}}},
        ],
        "forbidden_events": [{"match": {"type": "avp.error_occurred"}}],
        "final_state": {"stop_reason": "converged"},
    },
}

FAILING_CASE = {
    "id": "stub-missing-tool",
    "title": "stub agent never invokes the expected tool",
    "commission": {"schema_version": "0.1", "run_id": "stub-missing-tool", "model": "stub/mock"},
    "expectations": {
        "events": [{"match": {"type": "avp.tool_invoked"}}],
    },
}


def _setup(tmp_path: Path) -> Path:
    """Write the stub agent + its manifest under tmp_path; return manifest path."""
    agent_py = tmp_path / "stub_agent.py"
    agent_py.write_text(STUB_AGENT)
    manifest = tmp_path / "avp-conformance.json"
    manifest.write_text(
        json.dumps(
            {
                "command": [sys.executable, str(agent_py)],
                "cwd": ".",
                "env": {},
                "description": "stub conformance agent",
            }
        )
    )
    return manifest


def _write_case(tmp_path: Path, case: dict) -> Path:
    path = tmp_path / f"{case['id']}.json"
    path.write_text(json.dumps(case))
    return path


def test_check_passes_matching_trajectory(tmp_path):
    manifest = _setup(tmp_path)
    case = _write_case(tmp_path, PASSING_CASE)
    result = runner.invoke(app, ["check", "--agent", str(manifest), "--case", str(case)])
    assert result.exit_code == 0, result.output
    assert "PASS  stub-converges" in result.output


def test_check_fails_unmatched_expectation(tmp_path):
    manifest = _setup(tmp_path)
    case = _write_case(tmp_path, FAILING_CASE)
    result = runner.invoke(app, ["check", "--agent", str(manifest), "--case", str(case)])
    assert result.exit_code == 1
    assert "FAIL  stub-missing-tool" in result.output
    assert "tool_invoked" in result.output


def test_ping_passes_for_stub_agent(tmp_path):
    manifest = _setup(tmp_path)
    result = runner.invoke(app, ["ping", "--agent", str(manifest)])
    assert result.exit_code == 0, result.output
    assert "PASS  ping" in result.output
