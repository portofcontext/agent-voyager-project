"""`avp run` — commission one agent on one task inside a sandbox.

The real run is paid/agentic; here the sandbox stack and the agent run are
mocked at the cli seams and the tests assert the wiring: the task becomes the
Commission prompt, the env seeds the workspace the sandbox will mount, and a
missing container recipe skips cleanly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from avp_conformance.manifest import AgentManifest

from avp_cli import agent as agent_mod
from avp_cli import cli, osb
from avp_cli.agent import SandboxedAgent
from avp_cli.agents import NoContainerRecipe, ResolvedAgent


@pytest.fixture
def avp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    return tmp_path


def _stub_stack(monkeypatch, tmp_path):
    """Stub agent resolution, the sandbox server, and the image build."""
    agent = ResolvedAgent("goose", AgentManifest(command=["x"], cwd=".", env={}), tmp_path)
    monkeypatch.setattr(cli, "resolve_agent", lambda spec: agent)
    monkeypatch.setattr(
        cli.osb, "ensure_server", lambda: osb.Connection(domain="127.0.0.1:1", api_key="k")
    )
    monkeypatch.setattr(
        cli,
        "_prepare_agent",
        lambda agent, env_obj, quiet: SandboxedAgent(
            name=agent.name, image="img:test", command=("agent-bin",)
        ),
    )


def test_run_commissions_agent_with_task_in_env(avp_home, monkeypatch) -> None:
    _stub_stack(monkeypatch, avp_home)
    captured: dict = {}

    def fake_run_agent(agent, ctx, commission, *, out_path, timeout_s=300.0, on_event=None):
        captured["prompt"] = commission.prompt
        captured["agent"] = agent
        captured["ctx"] = ctx
        Path(out_path).write_text("")  # empty trajectory is fine
        return [], None

    monkeypatch.setattr(agent_mod, "run_agent", fake_run_agent)

    envfile = avp_home / "e.json"
    envfile.write_text('{"files": {"TASK.md": "context here"}}')

    rc = cli.main(["run", "--agent", "goose", "--env", str(envfile), "do the task"])
    assert rc == 0
    assert captured["prompt"] == "do the task"  # task becomes the Commission prompt
    assert captured["agent"].image == "img:test"  # runs the prepared sandbox image
    ctx = captured["ctx"]
    # env seeded into the workspace the sandbox mounts; it persists for inspection
    assert (ctx.workspace / "TASK.md").read_text() == "context here"
    assert ctx.workspace.exists()


def test_run_without_env_uses_default_world(avp_home, monkeypatch) -> None:
    _stub_stack(monkeypatch, avp_home)
    captured: dict = {}

    def fake_run_agent(agent, ctx, commission, *, out_path, timeout_s=300.0, on_event=None):
        captured["ctx"] = ctx
        Path(out_path).write_text("")
        return [], None

    monkeypatch.setattr(agent_mod, "run_agent", fake_run_agent)
    assert cli.main(["run", "--agent", "goose", "hello"]) == 0
    # no --env: still sandboxed, with an empty seeded workspace
    assert captured["ctx"].workspace.exists()
    assert list(captured["ctx"].workspace.iterdir()) == []


def test_run_skips_when_agent_has_no_recipe(avp_home, monkeypatch) -> None:
    agent = ResolvedAgent("custom", AgentManifest(command=["x"], cwd=".", env={}), avp_home)
    monkeypatch.setattr(cli, "resolve_agent", lambda spec: agent)
    monkeypatch.setattr(
        cli.osb, "ensure_server", lambda: osb.Connection(domain="127.0.0.1:1", api_key="k")
    )

    def no_recipe(agent):
        raise NoContainerRecipe("no container recipe")

    monkeypatch.setattr(cli, "container_recipe", no_recipe)
    # no recipe -> clean skip (exit 2), not a crash
    assert cli.main(["run", "--agent", "custom", "x"]) == 2


def test_run_fails_fast_without_docker(avp_home, monkeypatch) -> None:
    agent = ResolvedAgent("goose", AgentManifest(command=["x"], cwd=".", env={}), avp_home)
    monkeypatch.setattr(cli, "resolve_agent", lambda spec: agent)

    def no_docker():
        raise osb.SandboxUnavailable("Docker is not installed.")

    monkeypatch.setattr(cli.osb, "ensure_server", no_docker)
    # sandbox is mandatory: no Docker -> exit 2 before any work
    assert cli.main(["run", "--agent", "goose", "x"]) == 2


def test_builtin_claude_recipe_carries_is_sandbox_env() -> None:
    # The claude CLI refuses bypassPermissions as the container's root user
    # unless IS_SANDBOX=1; the recipe is where that knowledge lives.
    from avp_cli.agents import AGENT_SOURCES, _builtin_recipe

    recipe = _builtin_recipe(AGENT_SOURCES["claude-code"])
    assert ("IS_SANDBOX", "1") in recipe.env
    assert _builtin_recipe(AGENT_SOURCES["goose"]).env == ()
