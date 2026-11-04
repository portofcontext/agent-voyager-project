"""The built-in source pin and archive boundary, before any image is built."""

import hashlib
import io
import tarfile
from contextlib import nullcontext
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from avp_cli.agents import builtins
from avp_cli.cli import app
from avp_cli.console import Failed


def archive(name: str, *, link: bool = False) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as output:
        member = tarfile.TarInfo(name)
        if link:
            member.type = tarfile.SYMTYPE
            member.linkname = "/tmp/outside"
            output.addfile(member)
        else:
            content = b"agent source"
            member.size = len(content)
            output.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


def download(monkeypatch: pytest.MonkeyPatch, content: bytes, digest: str | None = None) -> None:
    source = builtins.Catalog(
        commit="test",
        sha256=digest or hashlib.sha256(content).hexdigest(),
        agents={"pydantic-ai": builtins.Agent("avp-pydantic-ai", "1.0", "agents/example")},
    )
    monkeypatch.setattr(builtins, "catalog", lambda: source)

    def stream(method: str, url: str, **kwargs: object) -> object:
        assert url.endswith("/tar.gz/test")
        return nullcontext(httpx.Response(200, content=content, request=httpx.Request(method, url)))

    monkeypatch.setattr(builtins.httpx, "stream", stream)


def test_verified_source_and_packaged_dockerfile_form_the_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download(monkeypatch, archive("agent-voyager-project-test/agents/example/main.py"))
    with builtins.context("pydantic-ai") as directory:
        assert (directory / "main.py").read_text() == "agent source"
        assert (directory / "Dockerfile").read_bytes() == (
            builtins.PACKAGE / "dockerfiles/pydantic-ai.Dockerfile"
        ).read_bytes()
    assert not directory.exists()


def test_checksum_mismatch_stops_before_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    download(monkeypatch, b"not an archive", digest="0" * 64)
    with pytest.raises(Failed, match="SHA-256"), builtins.context("pydantic-ai"):
        pytest.fail("accepted an unverified archive")


@pytest.mark.parametrize(
    ("name", "link", "message"),
    [
        ("agent-voyager-project-test/agents/example/../../outside", False, "unsafe path"),
        ("agent-voyager-project-test/agents/example/link", True, "link or special file"),
        ("agent-voyager-project-test/agents/other/main.py", False, "does not contain"),
    ],
)
def test_archive_paths_and_links_are_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, link: bool, message: str
) -> None:
    download(monkeypatch, archive(name, link=link))
    with pytest.raises(Failed, match=message), builtins.context("pydantic-ai"):
        pytest.fail("accepted an unsafe or missing agent source")


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


def test_list_builtins_shows_pinned_versions() -> None:
    result = CliRunner().invoke(app, ["agent", "list", "--builtin"])
    assert result.exit_code == 0, result.output
    for name, agent in builtins.catalog().agents.items():
        assert name in result.output
        assert agent.version in result.output
