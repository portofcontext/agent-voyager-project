"""`avp sandbox status` and `stop` with --verbose, against a scratch AVP home and
a stand-in for the service."""

import subprocess
from pathlib import Path

import pytest
from keyring.errors import NoKeyringError
from typer.testing import CliRunner

from avp_cli import engine, paths
from avp_cli.cli import app
from avp_cli.console import Failed
from avp_cli.sandbox import sandboxes, service


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    paths.opensandbox().mkdir(parents=True)
    return paths.opensandbox()


def test_verbose_status_shows_the_config_the_service_started_with(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths.opensandbox_config().write_text(service.config_text())
    paths.opensandbox_pid().write_text("4242")
    monkeypatch.setattr(service, "running", lambda: True)
    monkeypatch.setattr(engine, "name", lambda: "Test Engine 1")

    quiet = CliRunner().invoke(app, ["sandbox", "status"])
    assert "Process" not in quiet.stderr

    result = CliRunner().invoke(app, ["sandbox", "status", "--verbose"])
    assert result.exit_code == 0, result.output
    assert "Process: 4242" in result.stderr
    assert f"Config: {paths.opensandbox_config()}" in result.stderr
    assert f"Exec daemon image: {service.EXECD_IMAGE}" in result.stderr
    assert f"Egress image: {service.EGRESS_IMAGE}, mode dns+nft" in result.stderr
    assert "api_key" not in paths.opensandbox_config().read_text()


def test_verbose_stop_names_the_process(home: Path) -> None:
    process = subprocess.Popen(["sleep", "60"])
    paths.opensandbox_pid().write_text(str(process.pid))
    result = CliRunner().invoke(app, ["sandbox", "stop", "--verbose"])
    assert result.exit_code == 0, result.output
    assert f"Stopped process {process.pid}" in result.stderr
    assert process.wait(timeout=5) != 0


def test_service_key_is_shared_through_keyring_and_never_written(
    memory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(service.KEY_ENV, raising=False)
    monkeypatch.setattr(engine, "client", lambda: None)
    monkeypatch.setattr(engine, "where", lambda: "test engine")
    launched: list[dict] = []
    monkeypatch.setattr(service, "running", lambda: bool(launched))

    class Process:
        pid = 4242

    def launch(args, **kwargs):
        launched.append({"args": args, **kwargs})
        return Process()

    monkeypatch.setattr(service.subprocess, "Popen", launch)
    service.start()
    key = launched[0]["env"][service.KEY_ENV]
    assert len(key) == 64
    assert memory.get_password(service.KEY_SERVICE, str(paths.opensandbox().resolve())) == key
    assert service._connection().get_api_key() == key  # A later command reads the same credential.
    assert key not in str(launched[0]["args"])
    configuration = service.config()
    assert configuration is not None
    assert "api_key" not in configuration["server"]
    for path in paths.opensandbox().iterdir():
        if path.is_file():
            assert key not in path.read_text()


def test_environment_key_does_not_need_a_credential_store(
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(service.KEY_ENV, "test-environment-key")
    monkeypatch.setattr(service.keyring, "get_password", lambda *args: pytest.fail("read keyring"))
    monkeypatch.setattr(service.keyring, "set_password", lambda *args: pytest.fail("wrote keyring"))
    assert service._api_key(create=True) == "test-environment-key"
    assert service._api_key() == "test-environment-key"
    assert not list(home.iterdir())


def test_unavailable_credential_store_requires_environment_key(
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(service.KEY_ENV, raising=False)

    def unavailable(*args):
        raise NoKeyringError()

    monkeypatch.setattr(service.keyring, "get_password", unavailable)
    with pytest.raises(Failed, match=service.KEY_ENV):
        service._api_key(create=True)
    assert not list(home.iterdir())


class Box:
    def __init__(self) -> None:
        self.kills = 0
        self.closed = False

    def kill(self) -> None:
        self.kills += 1

    def close(self) -> None:
        self.closed = True


def test_kill_all_deletes_open_sandboxes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    box = Box()
    monkeypatch.setattr(sandboxes.SandboxSync, "create", lambda *a, **k: box)
    monkeypatch.setattr(sandboxes.service, "connection", lambda: None)
    with sandboxes.sandbox("avp/pd"):
        sandboxes.kill_all()
        assert box.kills == 1
    assert (box.kills, box.closed) == (1, True)
    sandboxes.kill_all()
    assert box.kills == 1


def test_a_sandbox_is_deleted_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    box = Box()
    monkeypatch.setattr(sandboxes.SandboxSync, "create", lambda *a, **k: box)
    monkeypatch.setattr(sandboxes.service, "connection", lambda: None)
    with sandboxes.sandbox("avp/pd"):
        pass
    assert (box.kills, box.closed) == (1, True)
