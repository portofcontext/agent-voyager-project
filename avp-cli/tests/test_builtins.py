"""Built-in package installation needs no checkout or source download."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from avp_cli.agents import builtins
from avp_cli.cli import app
from avp_cli.console import Failed
from avp_cli.engine import images


def test_packaged_dockerfile_is_the_only_build_input() -> None:
    for name, agent in builtins.catalog().agents.items():
        with builtins.context(name) as directory:
            assert list(directory.iterdir()) == [directory / "Dockerfile"]
            text = (directory / "Dockerfile").read_text()
            assert f"agent-{name}-v{agent.version}/" in text
            assert "COPY agents/" not in text
            assert "COPY avp-sdk/" not in text
        assert not directory.exists()


def test_unknown_name_lists_builtins_and_custom_names_cannot_replace_them(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(app, ["agent", "install", "unknown-agent"])
    assert isinstance(unknown.exception, Failed)
    for name in builtins.catalog().agents:
        assert name in str(unknown.exception)
    custom = runner.invoke(app, ["agent", "install", "pydantic-ai", str(tmp_path / "Dockerfile")])
    assert isinstance(custom.exception, Failed)
    assert "choose another name" in str(custom.exception)
    context = runner.invoke(app, ["agent", "install", "pydantic-ai", "--context", str(tmp_path)])
    assert isinstance(context.exception, Failed)
    assert "requires a custom Dockerfile" in str(context.exception)
    build = runner.invoke(
        app, ["agent", "install", "mine", str(tmp_path / "Dockerfile"), "--build"]
    )
    assert isinstance(build.exception, Failed)
    assert "--build is for built-in agents" in str(build.exception)


def test_failed_pull_points_to_a_package_build(monkeypatch: pytest.MonkeyPatch) -> None:
    pinned = builtins.Catalog(
        agents={"pydantic-ai": builtins.Agent("avp-pydantic-ai", "1.0", "pinned")},
    )
    monkeypatch.setattr(builtins, "catalog", lambda: pinned)

    def pull(reference: str, tag: str, progress: object = None) -> str:
        raise Failed(f"couldn't pull {reference}: denied")

    monkeypatch.setattr(images, "pull", pull)
    result = CliRunner().invoke(app, ["agent", "install", "pydantic-ai"])
    assert isinstance(result.exception, Failed)
    assert "couldn't pull pinned: denied" in str(result.exception)
    assert "avp agent install pydantic-ai --build" in str(result.exception)


def test_list_builtins_shows_pinned_versions() -> None:
    result = CliRunner().invoke(app, ["agent", "list", "--builtin"])
    assert result.exit_code == 0, result.output
    for name, agent in builtins.catalog().agents.items():
        assert name in result.output
        assert agent.version in result.output
