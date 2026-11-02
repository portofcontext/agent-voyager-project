"""`avp sandbox status` and `stop` with --verbose, against a scratch AVP home and
a stand-in for the service."""

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avp_cli import engine, paths
from avp_cli.cli import app
from avp_cli.sandbox import service


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    paths.opensandbox().mkdir(parents=True)
    return paths.opensandbox()


def test_verbose_status_shows_the_config_the_service_started_with(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (home / "config.toml").write_text(service.config_text("api-key-1"))
    (home / "server.pid").write_text("4242")
    monkeypatch.setattr(service, "running", lambda: True)
    monkeypatch.setattr(engine, "name", lambda: "Test Engine 1")

    quiet = CliRunner().invoke(app, ["sandbox", "status"])
    assert "Process" not in quiet.stderr

    result = CliRunner().invoke(app, ["sandbox", "status", "--verbose"])
    assert result.exit_code == 0, result.output
    assert "Process: 4242" in result.stderr
    assert f"Config: {home / 'config.toml'}" in result.stderr
    assert f"Exec daemon image: {service.EXECD_IMAGE}" in result.stderr
    assert f"Egress image: {service.EGRESS_IMAGE}, mode dns+nft" in result.stderr
    assert "api-key-1" not in result.output


def test_verbose_stop_names_the_process(home: Path) -> None:
    process = subprocess.Popen(["sleep", "60"])
    (home / "server.pid").write_text(str(process.pid))
    result = CliRunner().invoke(app, ["sandbox", "stop", "--verbose"])
    assert result.exit_code == 0, result.output
    assert f"Stopped process {process.pid}" in result.stderr
    assert process.wait(timeout=5) != 0
