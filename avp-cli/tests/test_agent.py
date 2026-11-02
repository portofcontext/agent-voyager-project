"""`avp agent` against a real container engine and OpenSandbox. Skipped when no
engine answers."""

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avp_cli import engine
from avp_cli.cli import app
from avp_cli.console import Failed
from avp_cli.engine import images
from avp_cli.sandbox import service

AGENT = Path(__file__).parent / "agent"


def engine_answers() -> bool:
    try:
        engine.client()
    except Failed:
        return False
    return True


TEST_PORT = 18799

pytestmark = pytest.mark.skipif(not engine_answers(), reason="no container engine answers")


@pytest.fixture(scope="module")
def avp_home(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path]:
    home = tmp_path_factory.mktemp("avp")
    with pytest.MonkeyPatch.context() as patch:
        # Its own port, so it never meets the service on avp's.
        patch.setattr(service, "PORT", TEST_PORT)
        if service.running():
            pytest.skip(f"an OpenSandbox service is already running on {TEST_PORT}")
        patch.setenv("AVP_HOME", str(home))
        yield home
        service.stop()


def avp(*args: str) -> str:
    result = CliRunner().invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_install_run_uninstall(avp_home: Path, tmp_path: Path) -> None:
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
    assert events[0]["data"]["commission"] == commission

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
