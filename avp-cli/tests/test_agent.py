"""`avp agent` against a real container engine and OpenSandbox. Skipped when no
engine answers."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avp_cli import engine
from avp_cli.agents import builtins
from avp_cli.cli import app
from avp_cli.console import Failed
from avp_cli.engine import images

AGENT = Path(__file__).parent / "agent"


def engine_answers() -> bool:
    try:
        engine.client()
    except Failed:
        return False
    return True


pytestmark = pytest.mark.skipif(not engine_answers(), reason="no container engine answers")


def avp(*args: str) -> str:
    result = CliRunner().invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_install_builtin_without_checkout(
    avp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    avp("agent", "install", "pydantic-ai")
    try:
        assert "pong" in avp("agent", "ping", "pydantic-ai")
        descriptor = json.loads(avp("agent", "describe", "pydantic-ai"))
        expected = builtins.get("pydantic-ai")
        assert descriptor["agent_name"] == expected.agent_name
        assert descriptor["agent_version"] == expected.version
        checked = avp(
            "conformance", "check", "--agent", "pydantic-ai", "--rule", "trajectory.4.1", "--json"
        )
        [outcome] = json.loads(checked[checked.index("[") :])
        assert outcome["status"] == "pass", outcome
    finally:
        avp("agent", "uninstall", "pydantic-ai")


def test_install_run_uninstall(
    avp_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    avp("agent", "install", "sh-agent", str(AGENT / "Dockerfile"))
    assert "sh-agent" in avp("agent", "list")
    assert json.loads(avp("agent", "describe", "sh-agent"))["agent_name"] == "sh-agent"
    pinged = avp("agent", "ping", "sh-agent", "--verbose")
    assert "pong" in pinged
    assert "entrypoint /agent.sh" in pinged
    assert "Running /agent.sh ping" in pinged
    assert pinged.count("Creating sandbox") == 1

    commission = {
        "avp_version": "0.1",
        "run_id": "sh-run",
        "prompt": "hi",
        "model": {"provider": "anthropic", "id": "claude-haiku-4-5"},
    }
    (tmp_path / "c.json").write_text(json.dumps(commission))
    output = avp(
        "run", "--commission", str(tmp_path / "c.json"), "--agent", "sh-agent", "--verbose"
    )
    assert '"error_message": "sh-agent refuses every Commission"' in output
    assert "Allowed hosts: api.anthropic.com (model)" in output
    assert "Running /agent.sh run --commission /io/commission.json" in output
    [run_directory] = (avp_home / "runs").iterdir()
    events = [json.loads(line) for line in (run_directory / "trajectory.ndjson").open()]
    sent = json.loads((run_directory / "commission.json").read_text())
    assert sent["run_id"] != "sh-run"
    assert sent["supervisor"]["name"] == "avp-cli"
    assert events[0]["data"]["commission"] == sent
    assert all(e["run_id"] == sent["run_id"] for e in events)

    # The whole saved-Commission workflow uses the installed image and a real sandbox.
    assert "Commission is valid" in avp(
        "commission", "check", str(tmp_path / "c.json"), "--agent", "sh-agent"
    )
    avp("commission", "save", "baseline", str(tmp_path / "c.json"))
    assert "baseline" in avp("commission", "list")
    avp("run", "--commission", "baseline", "--agent", "sh-agent")
    runs = list((avp_home / "runs").iterdir())
    assert len(runs) == 2
    ids = {json.loads((p / "commission.json").read_text())["run_id"] for p in runs}
    assert len(ids) == 2

    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                **commission,
                "skills": [
                    {"name": "guide", "files": {"SKILL.md": "no frontmatter"}},
                ],
            }
        )
    )
    with monkeypatch.context() as patch:
        from avp_cli.agents import command
        from avp_cli.runs import cli as run_cli

        patch.setattr(command, "describe_in_sandbox", lambda *a: pytest.fail("started describe"))
        patch.setattr(run_cli, "dispatch", lambda *a, **kw: pytest.fail("started run"))
        invalid = CliRunner().invoke(app, ["run", "--commission", str(bad), "--agent", "sh-agent"])
        assert invalid.exit_code == 1
        assert isinstance(invalid.exception, Failed)
        assert "SKILL.md" in str(invalid.exception)
    assert len(list((avp_home / "runs").iterdir())) == 2

    # sh-agent refuses every Commission, which is what this case expects.
    args = ["conformance", "check", "--agent", "sh-agent", "--concurrency", "4", "--json"]
    checked = avp(*args, "--rule", "commission.5.1")
    outcomes = json.loads(checked[checked.index("[") :])
    # Its Descriptor lists no items, so the cases that need one skip.
    skipped = {"enabled-tools-names-mcp-tool", "added-server-id-taken", "added-skill-name-taken"}
    assert {o["case"] for o in outcomes if o["status"] == "skip"} == skipped, outcomes
    passed = [o for o in outcomes if o["status"] == "pass"]
    assert len(passed) == len(outcomes) - len(skipped), outcomes
    for outcome in passed:
        assert outcome["run_directory"].startswith(str(avp_home / "conformance"))
        assert Path(outcome["run_directory"], "trajectory.ndjson").is_file()

    # -v and --entrypoint run code from the host, for describe and for the run.
    develop = tmp_path / "develop"
    develop.mkdir()
    script = develop / "agent.sh"
    script.write_text((AGENT / "agent.sh").read_text().replace('"1.0.0"', '"9.9.9"'))
    script.chmod(0o755)
    checked = avp(
        "conformance",
        "check",
        "--agent",
        "sh-agent",
        "--case",
        "agents-without-entry",
        "--json",
        "-v",
        f"{develop}:/develop:ro",
        "--entrypoint",
        "/develop/agent.sh",
    )
    [outcome] = json.loads(checked[checked.index("[") :])
    assert outcome["status"] == "pass", outcome
    run = Path(outcome["run_directory"])
    saved = json.loads((run.parent.parent / "agents" / "sh-agent.json").read_text())
    assert saved["descriptor"]["agent_version"] == "9.9.9"
    described = json.loads((run / "trajectory.ndjson").read_text().splitlines()[1])
    assert described["data"]["descriptor"]["agent_version"] == "9.9.9"

    # Its refusal isn't what commission.5.4 expects, but the runs start, with
    # servers that can't connect in their Commissions.
    result = CliRunner().invoke(app, [*args, "--rule", "commission.5.4"])
    assert result.exit_code == 1, result.output
    for outcome in json.loads(result.output[result.output.index("[") :]):
        assert outcome["status"] == "fail", outcome
        assert "not mcp_connect_failed" in "\n".join(outcome["reasons"]), outcome

    # An eval runs each item through the same dispatch, in its own sandbox.
    eval_file = tmp_path / "hi.eval.json"
    eval_file.write_text(
        json.dumps(
            {
                "eval_version": "0.1",
                "name": "hi",
                "agents": "sh-agent",
                "commission": "baseline",
                "dataset": [{"id": "a", "answer": "hello"}],
                "scorer": {"name": "match", "expected": "{item.answer}"},
            }
        )
    )
    saved = json.loads(avp("eval", "run", str(eval_file), "--json"))
    [run] = saved["runs"]
    assert (run["item"], run["exit_code"], run["score"]["passed"]) == ("a", 0, False)
    [eval_directory] = (avp_home / "evals").iterdir()
    assert (eval_directory / run["directory"] / "trajectory.ndjson").is_file()
    agent_record = json.loads((eval_directory / "agents" / "sh-agent.json").read_text())
    assert agent_record["descriptor"]["agent_name"] == "sh-agent"
    assert agent_record["image_id"].startswith("sha256:")

    avp("agent", "uninstall", "sh-agent")
    assert "sh-agent" not in avp("agent", "list")


@pytest.mark.parametrize(
    ("entrypoint", "message"),
    [("", "has no ENTRYPOINT"), ("ENTRYPOINT /agent.sh", "shell form")],
)
def test_entrypoint_must_be_exec_form(tmp_path: Path, entrypoint: str, message: str) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(f"FROM docker.io/library/alpine:3.20\n{entrypoint}\n")
    image = images.build(dockerfile, tmp_path, tag="localhost/avp/test-entrypoint")
    try:
        with pytest.raises(Failed, match=message):
            images.entrypoint(image)
    finally:
        images.remove(image)


def test_failed_build_shows_the_end_of_its_output(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM docker.io/library/alpine:3.20\nRUN echo the-last-words && false\n")
    with pytest.raises(Failed, match=r"(?s)The build's output ends:.*the-last-words"):
        images.build(dockerfile, tmp_path, tag="localhost/avp/test-failed-build")


def test_build_reports_each_step_and_the_ones_it_reuses() -> None:
    steps: list[images.Step] = []
    tag = "localhost/avp/test-steps"
    try:
        images.build(AGENT / "Dockerfile", AGENT, tag=tag)
        images.build(AGENT / "Dockerfile", AGENT, tag=tag, step=steps.append)
    finally:
        images.remove(tag)
    assert steps[0] == images.Step("1/3", "FROM docker.io/library/alpine:3.20")
    assert images.Step("2/3", "COPY agent.sh /agent.sh", cached=True) in steps
    assert steps[-1].number == "3/3"
