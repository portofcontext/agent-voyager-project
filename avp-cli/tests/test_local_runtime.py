"""Real local subprocesses: CLI -> file contract -> Recorder -> scored board."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from avp.commission import Commission
from avp_cli import cli, library, run_manifest, runtime
from avp_cli.agent import PreparedAgent, RunContext, run_agent

SCRIPT = r"""
import asyncio, json, os, subprocess, sys, time
from pathlib import Path
from avp.agent_cli import main
from avp.content import TextBlock
from avp.descriptor import AgentDescriptor
from avp.recorder import Recorder
from avp.trajectory import StopReason, Usage

def describe():
    return AgentDescriptor(agent_name="local-test", agent_version="0.0.0", spec_version="0.1")

async def run(cm, sink):
    rec = Recorder(sink, run_id=cm.run_id, provider="test")
    await rec.prelude(cm, describe())
    await rec.start(request_model=cm.model, prompt=cm.prompt)
    observed = {k: os.environ.get(k) for k in (
        "HOME", "AVP_HOME", "AVP_ENV_ROOT", "AVP_WORKSPACE", "CODEX_HOME",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AVP_VAULT_SECRET", "CUSTOM",
        "AVP_TEST_CUSTOM_SETTING", "NODE_EXTRA_CA_CERTS",
    )}
    observed["cwd"] = str(Path.cwd())
    Path(f"{cm.run_id}.env.json").write_text(json.dumps(observed))
    if cm.prompt in ("hang", "orphan"):
        child = subprocess.Popen([sys.executable, "-c",
            "import time; from pathlib import Path; time.sleep(1.5); Path('orphan').write_text('alive')"])
        Path("child.pid").write_text(str(child.pid))
        if cm.prompt == "hang":
            time.sleep(30)
    if cm.prompt == "fail":
        print("test failure", file=sys.stderr)
        sys.exit(7)
    if cm.prompt == "malformed":
        Path(sys.argv[sys.argv.index("--out") + 1]).write_text("not JSON\n")
        sys.exit(0)
    if cm.prompt == "nested":
        home = Path(os.environ["AVP_HOME"])
        (home / "commissions").mkdir(parents=True)
        (home / "commissions/inner.json").write_text(json.dumps({
            "schema_version": "0.1", "run_id": "inner", "model": "test/model", "prompt": "{input}"
        }))
        Path("inner-agent.json").write_text(json.dumps({"command": [sys.executable, __file__]}))
        Path("inner.eval.json").write_text(json.dumps({
            "agents": [str(Path("inner-agent.json").resolve())],
            "dataset": {"source": "inline", "items": [{"prompt": "ok", "expected": "ok"}]},
            "scorer": {"name": "exact-match"}, "commissions": ["inner"]
        }))
        subprocess.run([
            sys.executable, "-m", "avp_cli.cli", "eval", "run", "inner.eval.json",
            "--runtime", "local", "--json", "inner-board.json", "--quiet"
        ], check=True)
    if cm.prompt == "broker":
        import urllib.request
        req = urllib.request.Request(os.environ["OPENAI_BASE_URL"] + "/probe",
            headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}, data=b"{}")
        with urllib.request.urlopen(req) as response:
            assert response.status == 200
    await rec.assistant([TextBlock(text="ok")], Usage(input_tokens=1, output_tokens=1), model=cm.model)
    await asyncio.sleep(0.15)
    Path("finished").write_text("yes")
    await rec.stop(StopReason.converged, "ok")

raise SystemExit(main(run=run, describe=describe, prog="local-test"))
"""


@pytest.fixture
def local_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("AVP_HOME", str(tmp_path / "operator-home"))
    script = tmp_path / "agent.py"
    script.write_text(SCRIPT)
    manifest = tmp_path / "agent.json"
    manifest.write_text(
        json.dumps({"command": [sys.executable, "agent.py"], "env": {"CUSTOM": "manifest"}})
    )

    # Neither local CLI path may query Docker or prepare a container recipe.
    def forbidden(*a, **kw):
        pytest.fail("local execution touched the container backend")

    monkeypatch.setattr(cli.osb, "ensure_server", forbidden)
    monkeypatch.setattr(cli, "container_recipe", forbidden)
    agent = PreparedAgent(
        "local-test",
        None,
        (sys.executable, "agent.py"),
        env={"CUSTOM": "manifest"},
        cwd=tmp_path,
    )
    ctx = RunContext(None, tmp_path / "workspace", runtime="local")
    return manifest, agent, ctx


def commission(prompt="ok", run_id="trial"):
    return Commission(schema_version="0.1", run_id=run_id, model="openai/test", prompt=prompt)


def test_local_streams_and_separates_state_preserving_workspace(local_agent, tmp_path, monkeypatch):
    _, agent, ctx = local_agent
    monkeypatch.setenv("OPENAI_API_KEY", "selected-provider")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "other-provider")
    monkeypatch.setenv("AVP_VAULT_SECRET", "private")
    monkeypatch.setenv("AVP_TEST_CUSTOM_SETTING", "caller-config")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/custom/certificate.pem")
    monkeypatch.setenv("CUSTOM", "caller-value")
    ctx.setup = ["echo seeded > setup.txt"]
    streamed = []

    def observe(event):
        if event.type == "avp.assistant_message":
            assert not (ctx.workspace / "finished").exists()
        streamed.append(event.type)

    for rid in ("first", "second"):
        (ctx.workspace / "finished").unlink(missing_ok=True)
        events, err = run_agent(
            agent,
            ctx,
            commission(run_id=rid),
            out_path=tmp_path / f"{rid}.ndjson",
            on_event=observe,
        )
        assert err is None
        assert events[-1].data.output == "ok"
    first = json.loads((ctx.workspace / "first.env.json").read_text())
    second = json.loads((ctx.workspace / "second.env.json").read_text())
    assert first["HOME"] != second["HOME"]
    assert first["cwd"] == str(ctx.workspace.resolve())
    assert first["AVP_WORKSPACE"] == first["cwd"]
    assert first["OPENAI_API_KEY"] == "selected-provider"
    assert first["ANTHROPIC_API_KEY"] == "other-provider"
    assert first["AVP_VAULT_SECRET"] == "private"
    assert first["AVP_TEST_CUSTOM_SETTING"] == "caller-config"
    assert first["NODE_EXTRA_CA_CERTS"] == "/custom/certificate.pem"
    assert first["CUSTOM"] == "manifest"
    assert not Path(first["AVP_ENV_ROOT"]).exists()
    assert (ctx.workspace / "setup.txt").read_text().strip() == "seeded"
    assert "avp.agent_started" in streamed and "avp.agent_stopped" in streamed


@pytest.mark.parametrize("prompt", ["hang", "orphan"])
def test_local_cleans_up_tool_children_and_keeps_partial_output(local_agent, tmp_path, prompt):
    _, agent, ctx = local_agent
    out = tmp_path / "trajectory.ndjson"
    events, err = run_agent(agent, ctx, commission(prompt), out_path=out, timeout_s=0.9)
    if prompt == "hang":
        assert events is None and "timed out" in err
    else:
        assert err is None
    assert out.exists() and "avp.agent_started" in out.read_text()
    time.sleep(1.6)
    assert not (ctx.workspace / "orphan").exists()


def test_local_interrupt_retains_trajectory_and_cleans_state(local_agent, tmp_path):
    _, agent, ctx = local_agent

    def interrupt(event):
        if event.type == "avp.assistant_message":
            raise KeyboardInterrupt

    out = tmp_path / "interrupt.ndjson"
    with pytest.raises(KeyboardInterrupt):
        run_agent(agent, ctx, commission(), out_path=out, on_event=interrupt)
    assert "avp.assistant_message" in out.read_text()
    seen = json.loads((ctx.workspace / "trial.env.json").read_text())
    assert not Path(seen["AVP_ENV_ROOT"]).exists()
    assert not (ctx.workspace / "finished").exists()


@pytest.mark.parametrize("prompt, message", [("fail", "exit 7"), ("malformed", "local run failed")])
def test_local_failures_keep_diagnostics(local_agent, tmp_path, prompt, message):
    _, agent, ctx = local_agent
    out = tmp_path / "failed.ndjson"
    events, err = run_agent(agent, ctx, commission(prompt), out_path=out)
    assert events is None and message in err
    assert out.exists()
    if prompt == "fail":
        assert "test failure" in out.with_suffix(".stderr.log").read_text()


def test_cli_local_run_can_launch_a_nested_eval(local_agent, tmp_path):
    manifest, _, _ = local_agent
    assert (
        cli.main(
            [
                "run",
                "--agent",
                str(manifest),
                "--runtime",
                "local",
                "--model",
                "test/model",
                "nested",
            ]
        )
        == 0
    )
    run = next((tmp_path / "operator-home/runs").iterdir())
    assert run_manifest.read(run)["run"]["runtime"] == "local"
    board = json.loads((run / "workspace/inner-board.json").read_text())
    assert board["commissions"][0]["pass_rate"] == 1.0
    assert (run / "trajectory.ndjson").exists()


def test_cli_local_eval_scores_and_records_runtime(local_agent, tmp_path):
    manifest, _, _ = local_agent
    library.save("baseline", commission("{input}"))
    config = tmp_path / "test.eval.json"
    config.write_text(
        json.dumps(
            {
                "agents": [str(manifest)],
                "commissions": ["baseline"],
                "dataset": {
                    "source": "inline",
                    "items": [{"id": "one", "prompt": "ok", "expected": "ok"}],
                },
                "scorer": {"name": "exact-match"},
            }
        )
    )
    out = tmp_path / "results"
    assert (
        cli.main(
            [
                "eval",
                "run",
                str(config),
                "--runtime",
                "local",
                "--out",
                str(out),
                "--json",
                str(tmp_path / "board.json"),
                "--quiet",
            ]
        )
        == 0
    )
    board = json.loads((tmp_path / "board.json").read_text())
    assert board["commissions"][0]["pass_rate"] == 1.0
    assert run_manifest.read(out)["run"]["runtime"] == "local"
    assert "runtime" in cli._resume_drift(out, cli.config.load_eval(config), "opensandbox")


@pytest.mark.parametrize(
    "block",
    [
        {"image": "python:3.12-slim"},
        {"packages": {"pip": ["requests"]}},
        {"net": ["example.com"]},
        {"resources": {"cpu": "2"}},
    ],
)
def test_local_refuses_container_environment_settings(local_agent, tmp_path, block):
    manifest, _, _ = local_agent
    env = tmp_path / "env.json"
    env.write_text(json.dumps(block))
    assert (
        cli.main(
            [
                "run",
                "--agent",
                str(manifest),
                "--runtime",
                "local",
                "--env",
                str(env),
                "--model",
                "test/model",
                "ok",
            ]
        )
        == 1
    )


def test_runtime_selection_is_explicit_and_unknown_values_fail(monkeypatch):
    monkeypatch.delenv("AVP_RUNTIME", raising=False)
    assert runtime.resolve_runtime_name(None) == "opensandbox"
    monkeypatch.setenv("AVP_RUNTIME", "local")
    assert runtime.resolve_runtime_name(None) == "local"
    assert runtime.resolve_runtime_name("opensandbox") == "opensandbox"
    monkeypatch.setenv("AVP_RUNTIME", "typo")
    with pytest.raises(ValueError, match="unknown runtime"):
        runtime.resolve_runtime_name(None)


def test_local_provider_routes_through_loopback_broker(local_agent, tmp_path, monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from avp.commission import Provider, SecretRef

    seen = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            seen.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("AVP_VAULT_TEST_KEY", "vault-value")
    _, agent, ctx = local_agent
    cm = commission("broker")
    cm.provider = Provider(
        id="openai",
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
        credential=SecretRef(vault="test-key"),
    )
    try:
        events, err = run_agent(agent, ctx, cm, out_path=tmp_path / "broker.ndjson")
        assert err is None and events[-1].data.output == "ok"
        assert seen == [("/v1/probe", "Bearer vault-value")]
        dump = (ctx.workspace / "trial.env.json").read_text()
        assert "vault-value" not in dump
        assert "vault-value" not in (tmp_path / "broker.ndjson").read_text()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("setup, error", [("exit 9", "exit 9"), ("sleep 5", "timed out")])
def test_local_setup_failure_stops_before_agent(local_agent, tmp_path, setup, error):
    _, agent, ctx = local_agent
    ctx.setup = [setup]
    events, err = run_agent(
        agent, ctx, commission(), out_path=tmp_path / "setup.ndjson", timeout_s=0.2
    )
    assert events is None and "setup failed" in err and error in err
    assert not (ctx.workspace / "trial.env.json").exists()
