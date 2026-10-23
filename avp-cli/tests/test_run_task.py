"""`avp run` — commission one agent on one task inside a sandbox.

The real run is paid/agentic; here the sandbox stack and the agent run are
mocked at the cli boundaries and the tests assert the wiring: the task becomes the
Commission prompt, the env seeds the workspace the sandbox will mount, and a
missing container recipe skips cleanly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from avp_conformance.manifest import AgentManifest

from avp_cli import agent as agent_mod
from avp_cli import cli, images, osb
from avp_cli.agent import PreparedAgent
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
        lambda agent, env_obj, quiet, runtime_name="opensandbox": PreparedAgent(
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

    rc = cli.main(
        [
            "run",
            "--agent",
            "goose",
            "--model",
            "anthropic/claude-haiku-4-5",
            "--env",
            str(envfile),
            "do the task",
        ]
    )
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
    assert (
        cli.main(["run", "--agent", "goose", "--model", "anthropic/claude-haiku-4-5", "hello"]) == 0
    )
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


def _eval_with(monkeypatch, tmp_path, prepare) -> int:
    """`_run_and_report` over two agents, `prepare` standing in for each one's
    sandbox preparation; nothing may run unless every agent is ready."""
    monkeypatch.setattr(
        cli,
        "resolve_agent",
        lambda spec: ResolvedAgent(spec, AgentManifest(command=["x"], cwd=".", env={}), tmp_path),
    )
    monkeypatch.setattr(cli, "_prepare_agent", prepare)

    def no_runs(*args, **kwargs):
        raise AssertionError("the eval ran with an agent missing")

    monkeypatch.setattr(cli, "run_matrix", no_runs)
    monkeypatch.setattr(cli.run_manifest, "write", no_runs)
    return cli._run_and_report(
        None,
        run_id="r",
        agent_specs=["pydantic-ai", "openai-agents"],
        out=tmp_path,
        json_path=None,
        max_items=None,
        model=None,
        quiet=True,
        sandbox_ctx=type("Ctx", (), {"runtime": "opensandbox"})(),
        env_obj=None,
    )


def test_eval_stops_when_an_agent_image_fails_to_build(avp_home, monkeypatch) -> None:
    def prepare(agent, env_obj, quiet, runtime_name="opensandbox"):
        if agent.name == "openai-agents":
            raise images.ImageBuildError("docker build failed: pypi unreachable")
        return PreparedAgent(name=agent.name, image="img:test", command=("agent-bin",))

    assert _eval_with(monkeypatch, avp_home, prepare) == 1


def test_eval_stops_when_an_agent_cannot_run_here(avp_home, monkeypatch) -> None:
    def prepare(agent, env_obj, quiet, runtime_name="opensandbox"):
        if agent.name == "openai-agents":
            return None
        return PreparedAgent(name=agent.name, image="img:test", command=("agent-bin",))

    assert _eval_with(monkeypatch, avp_home, prepare) == 2


def test_run_fails_when_the_agent_image_fails_to_build(avp_home, monkeypatch) -> None:
    _stub_stack(monkeypatch, avp_home)

    def failed(agent, env_obj, quiet, runtime_name="opensandbox"):
        raise images.ImageBuildError("docker build failed")

    monkeypatch.setattr(cli, "_prepare_agent", failed)
    assert cli.main(["run", "--agent", "goose", "--model", "openai/gpt-5-mini", "x"]) == 1


def test_run_with_commission_fills_its_input_and_keeps_its_mcp_servers(
    avp_home, monkeypatch
) -> None:
    from avp.commission import Commission, McpServerHttp, SecretRef
    from avp_cli import library

    library.save(
        "pctx",
        Commission(
            schema_version="0.1",
            run_id="pctx",
            model="anthropic/claude-haiku-4-5",
            prompt="Answer with the pctx tools: {input}",
            mcp_servers=[
                McpServerHttp(
                    type="http",
                    id="pctx",
                    url="https://mcp.pctx.ai/mcp",
                    auth=SecretRef(vault="pctx"),
                )
            ],
        ),
    )
    _stub_stack(monkeypatch, avp_home)
    captured: dict = {}

    def fake_run_agent(agent, ctx, commission, *, out_path, timeout_s=300.0, on_event=None):
        captured["commission"] = commission
        Path(out_path).write_text("")
        return [], None

    monkeypatch.setattr(agent_mod, "run_agent", fake_run_agent)

    assert cli.main(["run", "--agent", "goose", "--commission", "pctx", "who is on the team?"]) == 0
    c = captured["commission"]
    assert c.prompt == "Answer with the pctx tools: who is on the team?"
    assert c.model == "anthropic/claude-haiku-4-5"  # the Commission's model, no --model needed
    assert c.mcp_servers[0].auth.vault == "pctx"
    assert c.run_id != "pctx"  # a fresh run id per run


def test_run_rejects_a_commission_without_an_input_slot(avp_home, monkeypatch) -> None:
    from avp.commission import Commission
    from avp_cli import library

    library.save(
        "fixed",
        Commission(
            schema_version="0.1", run_id="fixed", model="anthropic/claude-haiku-4-5", prompt="hi"
        ),
    )
    assert cli.main(["run", "--agent", "goose", "--commission", "fixed", "x"]) == 1
