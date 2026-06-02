"""`avp run` — commission one agent on one task, optionally inside an env.

The real run is paid/agentic; here we mock the agent spawn and assert the
wiring: the task becomes the Commission prompt, the env is materialized and
threaded as `env_mat`, and the workspace persists for inspection.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from avp_conformance.manifest import AgentManifest

from avp_cli import agent as agent_mod
from avp_cli import cli
from avp_cli.agents import ResolvedAgent


@pytest.fixture
def avp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    return tmp_path


def _stub_agent(monkeypatch, tmp_path):
    agent = ResolvedAgent("goose", AgentManifest(command=["x"], cwd=".", env={}), tmp_path)
    monkeypatch.setattr(cli, "resolve_agent", lambda spec: agent)
    monkeypatch.setattr(cli, "preflight", lambda name: None)


def test_run_commissions_agent_with_task_in_env(avp_home, monkeypatch) -> None:
    _stub_agent(monkeypatch, avp_home)
    captured: dict = {}

    def fake_run_agent(
        manifest,
        cwd,
        commission,
        *,
        out_path,
        timeout_s=300.0,
        on_event=None,
        sandbox=False,
        env_mat=None,
    ):
        captured["prompt"] = commission.prompt
        captured["env_mat"] = env_mat
        captured["sandbox"] = sandbox
        Path(out_path).write_text("")  # empty trajectory is fine
        return [], None

    monkeypatch.setattr(agent_mod, "run_agent", fake_run_agent)

    envfile = avp_home / "e.json"
    envfile.write_text('{"files": {"TASK.md": "context here"}}')

    rc = cli.main(
        ["run", "--agent", "goose", "--env", str(envfile), "--sandbox", "off", "do the task"]
    )
    assert rc == 0
    assert captured["prompt"] == "do the task"  # task becomes the Commission prompt
    assert captured["sandbox"] is False
    mat = captured["env_mat"]
    assert mat is not None
    # env materialized; its seeded context is in the workspace, which persists
    assert (mat.workspace / "TASK.md").read_text() == "context here"
    assert mat.workspace.exists()


def test_run_without_env_still_works(avp_home, monkeypatch) -> None:
    _stub_agent(monkeypatch, avp_home)

    def fake_run_agent(
        manifest,
        cwd,
        commission,
        *,
        out_path,
        timeout_s=300.0,
        on_event=None,
        sandbox=False,
        env_mat=None,
    ):
        assert env_mat is None  # no --env: run in the agent's own cwd
        Path(out_path).write_text("")
        return [], None

    monkeypatch.setattr(agent_mod, "run_agent", fake_run_agent)
    assert cli.main(["run", "--agent", "goose", "--sandbox", "off", "hello"]) == 0


def test_run_skips_when_agent_not_ready(avp_home, monkeypatch) -> None:
    agent = ResolvedAgent("goose", AgentManifest(command=["x"], cwd=".", env={}), avp_home)
    monkeypatch.setattr(cli, "resolve_agent", lambda spec: agent)
    monkeypatch.setattr(cli, "preflight", lambda name: "the `claude` CLI is not on PATH")
    # preflight failure -> clean skip (exit 2), not a crash
    assert cli.main(["run", "--agent", "goose", "x"]) == 2
