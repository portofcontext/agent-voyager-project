"""Seam test: `avp-conformance check` ↔ agent subprocess.

Crosses the harness↔agent seam without a real model. A stub agent script
honors the agent CLI contract (`ping`, `describe`, `run --commission --out`)
by writing a canned NDJSON trajectory; the harness writes the Commission to a
temp file, spawns the stub, reads the trajectory back, and matches it. This
pins the parts a matcher unit test can't see: argument plumbing (including
the describe-derived `${AGENT_NAME}` identity), file round-trip, exit-code
semantics, and PASS/FAIL reporting.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from avp_conformance._app import _INVALID_KEY, _invalid_credentials, app
from typer.testing import CliRunner

runner = CliRunner()

# A stub agent: `ping` writes pong; `describe` writes a minimal AgentDescriptor
# (check uses it to learn the agent identity for `${AGENT_NAME}` expansion);
# `run` writes a fixed converged trajectory, ignoring the Commission contents
# (this test exercises plumbing, not a model).
STUB_AGENT = """\
import argparse, json, sys

# Well-formed span tree: prelude at the root, agent_stopped under the agent
# span. (The harness structure check validates this on every trajectory.)
_T = "a" * 32
_Z = "0" * 16
_AGENT = "3" * 16
def _s(span_id, parent):
    return {"trace_id": _T, "span_id": span_id, "parent_span_id": parent}

TRAJECTORY = [
    {"type": "avp.run_requested", "source": "avp://agent", "data": _s("1" * 16, _Z)},
    {"type": "avp.agent_described", "source": "avp://agent", "data": _s("2" * 16, _Z)},
    {"type": "avp.agent_started", "source": "avp://agent", "data": _s(_AGENT, _Z)},
    {"type": "avp.agent_stopped", "source": "avp://agent",
     "data": {**_s("5" * 16, _AGENT), "avp.reason": "converged"}},
]

DESCRIPTOR = {"agent_name": "stub-agent", "agent_version": "0.0.1", "spec_version": "0.1"}

p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd", required=True)
pp = sub.add_parser("ping"); pp.add_argument("--out", required=True)
pd = sub.add_parser("describe"); pd.add_argument("--out", required=True)
pr = sub.add_parser("run")
pr.add_argument("--commission", required=True)
pr.add_argument("--built-in", dest="built_in", required=False)
pr.add_argument("--out", required=True)
a = p.parse_args()
with open(a.out, "w") as f:
    if a.cmd == "ping":
        f.write(json.dumps({"type": "pong"}) + "\\n")
    elif a.cmd == "describe":
        f.write(json.dumps(DESCRIPTOR) + "\\n")
    else:
        # Echo the Commission onto run_requested, as real agents do.
        TRAJECTORY[0]["data"]["avp.commission"] = json.load(open(a.commission))
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


SUBAGENT_CASE = {
    "id": "stub-delegates",
    "title": "needs subagents the stub doesn't declare",
    "requires": ["subagents"],
    "commission": {"schema_version": "0.1", "run_id": "stub-delegates", "model": "stub/mock"},
    "expectations": {"events": [{"match": {"type": "avp.subagent_invoked"}}]},
}

SNAPSHOT_CASE = {
    "id": "stub-snapshot",
    "title": "run_requested echoes the Commission model",
    "commission": {"schema_version": "0.1", "run_id": "stub-snapshot", "model": "stub/mock"},
    "expectations": {
        "events": [
            {
                "match": {
                    "type": "avp.run_requested",
                    "data": {"avp.commission": {"model": "stub/mock"}},
                }
            }
        ]
    },
}


def test_case_requiring_an_undeclared_surface_is_skipped(tmp_path):
    manifest = _setup(tmp_path)
    case = _write_case(tmp_path, SUBAGENT_CASE)
    result = runner.invoke(app, ["check", "--agent", str(manifest), "--case", str(case)])
    assert result.exit_code == 0, result.output
    assert "SKIP  stub-delegates  (agent declares no subagents)" in result.output
    assert "0 pass, 0 fail, 1 skip" in result.output


def test_model_override_rewrites_commission_and_expectations(tmp_path):
    manifest = _setup(tmp_path)
    case = _write_case(tmp_path, SNAPSHOT_CASE)
    argv = ["check", "--agent", str(manifest), "--case", str(case), "--model", "openai/gpt-x"]
    dump = tmp_path / "dump"
    result = runner.invoke(app, [*argv, "--dump-dir", str(dump)])
    assert result.exit_code == 0, result.output
    assert "PASS  stub-snapshot" in result.output
    first = json.loads((dump / "stub-snapshot.jsonl").read_text().splitlines()[0])
    assert first["data"]["avp.commission"]["model"] == "openai/gpt-x"


def test_every_command_gets_fresh_launcher_owned_state(tmp_path, monkeypatch):
    from avp.launch import directory_env

    manifest = _setup(tmp_path)
    dump = tmp_path / "environments.jsonl"
    stub = tmp_path / "stub_agent.py"
    stub.write_text(
        "import os\n"
        + STUB_AGENT
        + f'\nwith open({str(dump)!r}, "a") as log:\n'
        + '    log.write(json.dumps(dict(os.environ)) + "\\n")\n'
    )
    for name in directory_env(tmp_path / "ambient"):
        monkeypatch.setenv(name, str(tmp_path / "ambient" / name))
    case = _write_case(tmp_path, PASSING_CASE)
    for cmd in (["ping"], ["describe"], ["check", "--case", str(case)]):
        result = runner.invoke(app, [*cmd, "--agent", str(manifest)])
        assert result.exit_code == 0, result.output
    environments = [json.loads(line) for line in dump.read_text().splitlines()]
    roots = [Path(env["AVP_ENV_ROOT"]) for env in environments]
    assert len(set(roots)) == 4  # ping, describe, check's describe, check's run
    for env, root in zip(environments, roots, strict=True):
        for name in directory_env(root):
            assert Path(env[name]).is_relative_to(root)
        assert not root.exists()


def test_model_override_updates_native_provider_and_snapshot(tmp_path):
    from avp_conformance._utils import load_case

    path = (
        Path(__file__).parents[1]
        / "src/avp_conformance/cases/v0.1/security/commission-snapshot-carries-secret-handles.json"
    )
    case = load_case(path, str(path))
    manifest = _setup(tmp_path)
    dump = tmp_path / "dump"
    result = runner.invoke(
        app,
        [
            "check",
            "--agent",
            str(manifest),
            "--case",
            str(path),
            "--model",
            "openai/gpt-x",
            "--dump-dir",
            str(dump),
        ],
    )
    assert result.exit_code == 0, result.output
    first = json.loads((dump / f"{case.id}.jsonl").read_text().splitlines()[0])
    assert first["data"]["avp.commission"]["provider"] == {
        "id": "openai",
        "credential": {"vault": "anthropic"},
    }


def test_model_override_preserves_explicit_gateway_routing():
    from avp_conformance._app import with_model
    from avp_conformance.case import TestCase

    for provider in (
        {"id": "openrouter"},
        {"id": "anthropic", "base_url": "https://gateway.example/v1"},
    ):
        data = json.loads(json.dumps(PASSING_CASE))
        data["commission"].update(model="anthropic/claude-haiku-4-5", provider=provider)
        rewritten = with_model(TestCase.model_validate(data), "openai/gpt-x")
        assert rewritten.commission.model == "openai/gpt-x"
        assert rewritten.commission.provider.model_dump(exclude_none=True) == provider


# ── run conditions: invalid credentials, interrupts ─────────────────────────

# A stub whose `run` records its credential environment on agent_started, then
# (when told to by SLOW) waits for a signal and stops `interrupted`.
CONDITION_AGENT = """\
import json, os, signal, sys, time
_T, _Z, _AGENT = "a" * 32, "0" * 16, "3" * 16
def _s(span_id, parent):
    return {"trace_id": _T, "span_id": span_id, "parent_span_id": parent}
cmd = sys.argv[1]
out = sys.argv[sys.argv.index("--out") + 1]
if cmd == "describe":
    open(out, "w").write(json.dumps(
        {"agent_name": "stub", "agent_version": "0.0.1", "spec_version": "0.1"}))
    sys.exit(0)
keys = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
seen = {k: os.environ.get(k) for k in keys}
f = open(out, "w")
def emit(t, span, parent, **data):
    f.write(json.dumps({"type": t, "source": "avp://agent", "data": {**_s(span, parent), **data}}) + "\\n")
    f.flush()
emit("avp.run_requested", "1" * 16, _Z)
emit("avp.agent_described", "2" * 16, _Z)
emit("avp.agent_started", _AGENT, _Z, **{"avp.meta": seen})
if os.environ.get("SLOW"):
    def stop(*_):
        emit("avp.agent_stopped", "5" * 16, _AGENT, **{"avp.reason": "interrupted"})
        sys.exit(143)
    signal.signal(signal.SIGTERM, stop)
    time.sleep(30)
emit("avp.agent_stopped", "5" * 16, _AGENT, **{"avp.reason": "converged"})
"""


def _condition_setup(tmp_path: Path, env: dict) -> Path:
    agent_py = tmp_path / "condition_agent.py"
    agent_py.write_text(CONDITION_AGENT)
    manifest = tmp_path / "avp-conformance.json"
    manifest.write_text(
        json.dumps({"command": [sys.executable, str(agent_py)], "cwd": ".", "env": env})
    )
    return manifest


def _condition_case(stop_reason: str, **extra) -> dict:
    return {
        "id": "condition",
        "title": "run condition",
        "commission": {
            "schema_version": "0.1",
            "run_id": "c",
            "model": "anthropic/claude-haiku-4-5",
        },
        "expectations": {
            "events": [{"match": {"type": "avp.agent_stopped"}}],
            "final_state": {"stop_reason": stop_reason},
        },
        **extra,
    }


def test_invalid_credentials_replace_the_provider_key_and_drop_fallbacks(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "real-key")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "real-oauth")
    manifest = _condition_setup(tmp_path, {})
    case = _write_case(tmp_path, _condition_case("converged", credentials="invalid"))
    dump = tmp_path / "dump"
    result = runner.invoke(
        app, ["check", "--agent", str(manifest), "--case", str(case), "--dump-dir", str(dump)]
    )
    assert result.exit_code == 0, result.output
    started = [json.loads(line) for line in (dump / "condition.jsonl").read_text().splitlines()][2]
    assert started["data"]["avp.meta"] == {
        "ANTHROPIC_API_KEY": _INVALID_KEY,
        "CLAUDE_CODE_OAUTH_TOKEN": None,
    }
    openai = _invalid_credentials({"OPENAI_API_KEY": "real"}, "openai/gpt-5-mini")
    assert openai["OPENAI_API_KEY"] == _INVALID_KEY == openai["CODEX_API_KEY"]


def test_an_interrupt_signals_the_agent_and_judges_its_trajectory(tmp_path):
    manifest = _condition_setup(tmp_path, {"SLOW": "1"})
    interrupt = {"after": "avp.agent_started", "delay_s": 0.2, "signal": "SIGTERM"}
    case = _write_case(tmp_path, _condition_case("interrupted", interrupt=interrupt))
    result = runner.invoke(app, ["check", "--agent", str(manifest), "--case", str(case)])
    # Exit 143 is the agent's business; the interrupted trajectory passes.
    assert result.exit_code == 0, result.output
    assert "PASS  condition" in result.output


def test_an_agent_that_finishes_before_the_interrupt_point_fails(tmp_path):
    manifest = _condition_setup(tmp_path, {})
    interrupt = {"after": "avp.assistant_message", "signal": "SIGTERM"}
    case = _write_case(tmp_path, _condition_case("interrupted", interrupt=interrupt))
    result = runner.invoke(app, ["check", "--agent", str(manifest), "--case", str(case)])
    assert result.exit_code == 1
    assert "nothing to interrupt" in result.output


def test_a_timed_out_agent_is_killed_with_everything_it_launched(tmp_path):
    """A launcher (`uv run`, `cargo run`) can't forward SIGKILL: killing only
    it would leave the agent running after the case."""
    manifest = _setup(tmp_path)
    pid_file = tmp_path / "agent.pid"
    launcher = tmp_path / "launcher.sh"
    launcher.write_text(
        f'if [ "$1" = run ]; then sleep 300 & echo $! > {pid_file}; wait; '
        f'else exec {sys.executable} {tmp_path / "stub_agent.py"} "$@"; fi\n'
    )
    data = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({**data, "command": ["/bin/sh", str(launcher)]}))
    case = _write_case(tmp_path, PASSING_CASE)
    result = runner.invoke(
        app, ["check", "--agent", str(manifest), "--case", str(case), "--timeout", "2"]
    )
    assert result.exit_code == 1
    assert "timed out" in result.output
    pid = int(pid_file.read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    raise AssertionError(f"the launched agent (pid {pid}) outlived the case")
