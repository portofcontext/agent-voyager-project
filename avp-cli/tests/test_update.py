"""`avp update` and `avp agent update`, without GitHub, uv, or an engine."""

import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from packaging.version import Version
from typer.testing import CliRunner

from avp_cli import update
from avp_cli.agents import builtins, store
from avp_cli.agents import cli as agent_cli
from avp_cli.cli import app
from avp_cli.console import Failed

WHEEL = "https://github.test/download/cli-v{0}/avp_cli-{0}-py3-none-any.whl"


def release(tag: str, *, draft: bool = False, wheel: bool = True) -> dict[str, Any]:
    version = tag.removeprefix("cli-v")
    assets = [{"name": f"avp_cli-{version}.tar.gz", "browser_download_url": "https://sdist"}]
    if wheel:
        name = f"avp_cli-{version}-py3-none-any.whl"
        assets.append({"name": name, "browser_download_url": WHEEL.format(version)})
    return {"tag_name": tag, "draft": draft, "prerelease": True, "assets": assets}


def published(monkeypatch: pytest.MonkeyPatch, *listed: dict[str, Any], installed: str) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: httpx.Response(
            200, json=list(listed), request=httpx.Request("GET", update.RELEASES)
        ),
    )
    monkeypatch.setattr(update, "current", lambda: Version(installed))


def test_only_cli_releases_with_a_wheel_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    published(
        monkeypatch,
        release("sdk-python-v9.0.0"),
        release("cli-v0.8.0", draft=True),
        release("cli-v0.7.5", wheel=False),
        release("cli-vnot-a-version"),
        release("cli-v0.7.0"),
        installed="0.6.0",
    )
    assert update.releases() == [update.Release(Version("0.7.0"), WHEEL.format("0.7.0"))]


@pytest.mark.parametrize(
    ("installed", "pre", "expected"),
    [
        ("0.6.0", False, "0.7.0"),
        ("0.6.0", True, "0.8.0b1"),
        ("0.7.0b1", False, "0.8.0b1"),
        ("0.7.0", False, None),
        ("0.9.0", True, None),
    ],
)
def test_a_prerelease_is_newer_only_for_a_prerelease_or_with_pre(
    installed: str, pre: bool, expected: str | None
) -> None:
    found = [update.Release(Version(v), v) for v in ("0.6.0", "0.7.0", "0.8.0b1")]
    newest = update.newest(found, Version(installed), pre)
    assert (str(newest.version) if newest else None) == expected


def test_check_reports_and_installs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    published(monkeypatch, release("cli-v0.7.0"), installed="0.6.0")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("ran a command"))
    result = CliRunner().invoke(app, ["update", "--check"])
    assert result.exit_code == 0
    assert "avp 0.7.0 is available; this is 0.6.0" in result.output
    published(monkeypatch, release("cli-v0.7.0"), installed="0.7.0")
    assert "avp 0.7.0 is the newest release" in CliRunner().invoke(app, ["update"]).output


def test_update_installs_the_wheel_with_uv_then_updates_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published(monkeypatch, release("cli-v0.7.0"), installed="0.6.0")
    (tmp_path / update.RECEIPT).write_text("")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["/tools/bin/avp", "update"])
    monkeypatch.setattr(update, "checkout", lambda: None)
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/bin/{name}")
    ran: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        ran.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    result = CliRunner().invoke(app, ["update"])
    assert result.exit_code == 0, result.output
    assert ran == [
        ["uv", "tool", "install", "--force", WHEEL.format("0.7.0")],
        ["/tools/bin/avp", "agent", "update"],
    ]


def test_an_avp_uv_didnt_install_is_told_what_to_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published(monkeypatch, release("cli-v0.7.0"), installed="0.6.0")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("ran a command"))
    monkeypatch.setattr(update, "checkout", lambda: "file:///src/avp-cli")
    editable = CliRunner().invoke(app, ["update"])
    assert isinstance(editable.exception, Failed)
    assert "runs from a checkout, file:///src/avp-cli" in str(editable.exception)
    monkeypatch.setattr(update, "checkout", lambda: None)
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    other = CliRunner().invoke(app, ["update"])
    assert isinstance(other.exception, Failed)
    assert WHEEL.format("0.7.0") in str(other.exception)


def test_a_failed_install_shows_uvs_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    published(monkeypatch, release("cli-v0.7.0"), installed="0.6.0")
    (tmp_path / update.RECEIPT).write_text("")
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(update, "checkout", lambda: None)
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **k: subprocess.CompletedProcess(command, 2, "", "no network"),
    )
    result = CliRunner().invoke(app, ["update"])
    assert isinstance(result.exception, Failed)
    assert "no network" in str(result.exception)


def test_agent_update_reinstalls_only_outdated_builtins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    listed = builtins.catalog().agents
    current, outdated, unversioned = list(listed)[:3]
    store.save(store.Agent(name=current, image="a", version=listed[current].version))
    store.save(store.Agent(name=outdated, image="b", version="0.0.0"))
    store.save(store.Agent(name=unversioned, image="c"))
    store.save(store.Agent(name="my-agent", image="d", version="0.0.0"))
    installed: list[str] = []
    monkeypatch.setattr(agent_cli, "install", installed.append)
    result = CliRunner().invoke(app, ["agent", "update"])
    assert result.exit_code == 0, result.output
    assert sorted(installed) == sorted([outdated, unversioned])
    store.delete(outdated)
    store.delete(unversioned)
    assert "up to date" in CliRunner().invoke(app, ["agent", "update"]).output
