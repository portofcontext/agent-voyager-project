"""Installing agents (avp releases, custom manifests, local builds) and resolving them, offline.

Release downloads are stubbed at `_resolve_release` / `_download`. Python
installs need `uv` + network, so they're covered by the manual smoke in the PR;
binary and Node installs run end to end with fake artifacts.
"""

from __future__ import annotations

import json
import tarfile

import pytest

from avp_cli import agent_install, agents, images
from avp_cli.environment import Environment


@pytest.fixture
def avp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    monkeypatch.delenv("AVP_AGENT_REPO", raising=False)
    return tmp_path


@pytest.fixture
def linux_binary(tmp_path):
    p = tmp_path / "avp-goose-conformance"
    p.write_bytes(b"\x7fELF" + b"\0" * 60)
    return p


def _package(tmp_path, *, entry: str = "dist/src/main.js", name: str = "avp-pi.tar.gz"):
    """A minimal Node package archive shaped like the pi release asset."""
    root = tmp_path / "pkg"
    script = root / entry
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("console.log('pi')\n")
    archive = tmp_path / name
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname=".")
    return archive


def _manifest(tmp_path, *, container: bool = True):
    d = tmp_path / "my-agent"
    d.mkdir(exist_ok=True)
    body = {"command": ["my-agent"], "cwd": ".", "env": {}}
    if container:
        body["container"] = {"install": ["pip install my-agent"], "command": ["my-agent"]}
    (d / "avp-conformance.json").write_text(json.dumps(body))
    return d / "avp-conformance.json"


def _stub_release(monkeypatch, tmp_path, assets: dict[str, bytes], version: str = "0.1.0"):
    """Serve a fake release: `assets` maps asset name -> bytes."""
    listed = [{"name": n, "browser_download_url": f"https://x/{n}"} for n in assets]
    seen = {}

    def resolve(source, v, repo):
        seen["version"], seen["repo"] = v, repo
        return f"{source.tag_prefix}-v{v}", v, listed

    def download(url, dest):
        dest.write_bytes(assets[url.rsplit("/", 1)[1]])

    monkeypatch.setattr(agent_install, "_resolve_release", resolve)
    monkeypatch.setattr(agent_install, "_download", download)
    return seen


# ── avp releases ──────────────────────────────────────────────────────────────


def test_release_install_pins_the_cli_version_and_records_the_origin(
    avp_home, tmp_path, monkeypatch
) -> None:
    seen = _stub_release(monkeypatch, tmp_path, {"avp-pi.tar.gz": _package(tmp_path).read_bytes()})

    result = agent_install.install("pi")

    assert seen["version"] == agents.AGENT_SOURCES["pi"].container_version
    assert seen["repo"] == agents.CANONICAL_REPO
    assert result.source == "release"
    record = agents.installed_record("pi")
    assert record["from"] == "release" and record["agent"] == "pi"
    assert agents.origin_label(record) == f"avp release {seen['version']}"
    resolved = agents.resolve_agent("pi")
    assert resolved.origin == "release" and resolved.agent_name == "avp-pi"
    assert resolved.label is None  # boards keep the descriptor name for releases


def test_release_recipe_uses_the_installed_version_and_fork(
    avp_home, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("AVP_AGENT_REPO", "acme/avp-fork")
    _stub_release(
        monkeypatch, tmp_path, {"avp-pi.tar.gz": _package(tmp_path).read_bytes()}, version="9.9.9"
    )
    agent_install.install("pi", version="9.9.9")

    resolved = agents.resolve_agent("pi")
    assert resolved.origin_label == "avp release 9.9.9 (fork: acme/avp-fork)"
    recipe = agents.container_recipe(resolved)
    assert any("acme/avp-fork/releases/download/agent-pi-v9.9.9/" in s for s in recipe.install)


def test_per_platform_node_release_picks_the_host_archive(avp_home, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(agent_install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(agent_install.platform, "machine", lambda: "aarch64")
    archive = _package(tmp_path).read_bytes()
    _stub_release(
        monkeypatch,
        tmp_path,
        {"avp-opencode-linux-arm64.tar.gz": archive, "avp-opencode-linux-x64.tar.gz": b"x"},
    )
    result = agent_install.install("opencode")
    assert result.kind == "node"
    assert result.version == agents.AGENT_SOURCES["opencode"].container_version


def test_install_all_continues_past_failures(avp_home, tmp_path, monkeypatch) -> None:
    def fake(source, *, version=None, force=False):
        if source.name == "pi":
            raise agent_install.InstallError("`node` is not on PATH")
        d = agent_install._prepare_dir(source.name, force=True)
        agent_install._write_record(
            d, {"name": source.name, "from": "release", "agent": source.name, "version": "1"}
        )
        return agent_install.InstallResult(source.name, "1", source.kind, "release", d)

    monkeypatch.setattr(agent_install, "install_release", fake)
    first = list(agent_install.install_all())
    assert [n for n, _, _ in first] == list(agents.AGENT_SOURCES)
    assert [n for n, _, err in first if err] == ["pi"]

    again = {n: (r, e) for n, r, e in agent_install.install_all()}
    assert again["goose"] == (None, None)  # already installed: skipped
    assert again["pi"][1] is not None  # still failing, still retried


def test_not_installed_points_at_install_all(avp_home) -> None:
    with pytest.raises(SystemExit, match="avp agent install --all"):
        agents.resolve_agent("goose")


def test_no_checkout_fallback(avp_home) -> None:
    # Running from a source checkout no longer resolves in-repo manifests.
    assert not agents.is_installed("claude-code")
    with pytest.raises(SystemExit):
        agents.resolve_agent("claude-code")


def test_pre_origin_release_records_still_resolve(avp_home) -> None:
    d = avp_home / "agents" / "pi"
    d.mkdir(parents=True)
    (d / "installed.json").write_text(
        json.dumps({"name": "pi", "version": "0.1.0", "source": "release"})
    )
    (d / "avp-conformance.json").write_text(json.dumps({"command": ["node", "x"], "cwd": "."}))
    resolved = agents.resolve_agent("pi")
    assert resolved.origin == "release" and resolved.origin_label == "avp release 0.1.0"


# ── custom agents ─────────────────────────────────────────────────────────────


def test_manifest_install_resolves_by_name_and_uses_its_container(avp_home, tmp_path) -> None:
    path = _manifest(tmp_path)
    agent_install.install("my-agent", manifest=path)

    resolved = agents.resolve_agent("my-agent")
    assert resolved.origin == "manifest" and resolved.agent_name is None
    assert resolved.manifest.command == ["my-agent"]
    assert agents.container_recipe(resolved).install == ("pip install my-agent",)
    assert "my-agent" in agents.installed_agents()


def test_manifest_cannot_take_a_built_in_name(avp_home, tmp_path) -> None:
    with pytest.raises(agent_install.InstallError, match="built-in agent name"):
        agent_install.install("claude-code", manifest=_manifest(tmp_path))


def test_manifest_needs_a_container_block(avp_home, tmp_path) -> None:
    with pytest.raises(agent_install.InstallError, match="no `container` block"):
        agent_install.install("my-agent", manifest=_manifest(tmp_path, container=False))


def test_manifest_moved_after_install(avp_home, tmp_path) -> None:
    path = _manifest(tmp_path)
    agent_install.install("my-agent", manifest=path)
    path.unlink()
    with pytest.raises(SystemExit, match="no longer exists"):
        agents.resolve_agent("my-agent")


def test_unknown_name_without_manifest(avp_home) -> None:
    with pytest.raises(agent_install.InstallError, match="--manifest"):
        agent_install.install("nope")


def test_unregistered_manifest_path_still_runs(avp_home, tmp_path) -> None:
    resolved = agents.resolve_agent(str(_manifest(tmp_path)))
    assert resolved.origin == "unregistered" and resolved.name == "my-agent"
    assert "(not installed)" in resolved.origin_label


# ── local builds ──────────────────────────────────────────────────────────────


def test_local_build_needs_its_own_name(avp_home, linux_binary) -> None:
    with pytest.raises(agent_install.InstallError, match="--as goose-dev"):
        agent_install.install("goose", binary=linux_binary)
    with pytest.raises(agent_install.InstallError, match="built-in agent name"):
        agent_install.install("goose", binary=linux_binary, as_name="pi")


def test_local_binary_must_be_linux(avp_home, tmp_path) -> None:
    mac = tmp_path / "avp-goose-conformance"
    mac.write_bytes(b"\xcf\xfa\xed\xfe" + b"\0" * 60)  # Mach-O
    with pytest.raises(agent_install.InstallError, match="not a Linux binary"):
        agent_install.install("goose", binary=mac, as_name="goose-dev")


def test_local_build_is_labeled_and_copied_into_the_image(avp_home, tmp_path) -> None:
    agent_install.install("pi", package=_package(tmp_path), as_name="pi-dev")

    resolved = agents.resolve_agent("pi-dev")
    assert resolved.origin == "local" and resolved.origin_label == "local build of pi"
    assert resolved.agent_name == "avp-pi"  # Commissions keyed for pi still bind
    assert resolved.label == "pi-dev"  # but boards tell it apart
    record = agents.installed_record("pi-dev")
    assert list(record["artifacts"]) == ["avp-pi.tar.gz"]

    recipe = agents.container_recipe(resolved)
    assert recipe.context == str(avp_home / "agents" / "pi-dev" / "artifacts")
    df = images.dockerfile(Environment(), recipe)
    assert "COPY . /opt/avp-artifacts" in df
    assert "releases/download" not in df  # not the avp release

    before = images.image_tag(Environment(), recipe)
    (avp_home / "agents" / "pi-dev" / "artifacts" / "avp-pi.tar.gz").write_bytes(b"rebuilt")
    assert images.image_tag(Environment(), recipe) != before  # new artifacts, new image


def test_local_binary_recipe_installs_the_copied_binary(avp_home, linux_binary) -> None:
    agent_install.install("goose", binary=linux_binary, as_name="goose-dev")
    recipe = agents.container_recipe(agents.resolve_agent("goose-dev"))
    assert recipe.install == (
        "install -m 0755 /opt/avp-artifacts/avp-goose-conformance "
        "/usr/local/bin/avp-goose-conformance",
    )


def test_wrong_artifact_kind_rejected(avp_home, linux_binary, tmp_path) -> None:
    with pytest.raises(agent_install.InstallError, match="--wheel applies to python"):
        agent_install.install("goose", wheels=["/x.whl"], as_name="g")
    with pytest.raises(agent_install.InstallError, match="--binary applies to binary"):
        agent_install.install("claude-code", binary=linux_binary, as_name="c")
    with pytest.raises(agent_install.InstallError, match="--package applies to node"):
        agent_install.install("goose", package=_package(tmp_path), as_name="g")


def test_node_package_without_the_entry_is_rejected(avp_home, tmp_path) -> None:
    with pytest.raises(agent_install.InstallError, match="did not contain"):
        agent_install.install("pi", package=_package(tmp_path, entry="other.js"), as_name="pi-dev")
    assert not (avp_home / "agents" / "pi-dev").exists()


def test_reinstall_needs_force_and_uninstall(avp_home, linux_binary) -> None:
    agent_install.install("goose", binary=linux_binary, as_name="goose-dev")
    with pytest.raises(agent_install.InstallError, match="already installed"):
        agent_install.install("goose", binary=linux_binary, as_name="goose-dev")
    agent_install.install("goose", binary=linux_binary, as_name="goose-dev", force=True)
    assert agent_install.uninstall("goose-dev") is True
    assert agent_install.uninstall("goose-dev") is False


# ── host prerequisites ────────────────────────────────────────────────────────


def test_current_target_is_mac_or_linux() -> None:
    assert any(s in agent_install.current_target() for s in ("apple-darwin", "linux-gnu"))


def test_node_preflight_checks_the_runtime_version(monkeypatch) -> None:
    import subprocess

    monkeypatch.setattr(agents.shutil, "which", lambda _: "/usr/bin/node")

    def version(out):
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out)

    monkeypatch.setattr(agents.subprocess, "run", version("v22.17.1\n"))
    assert "needs Node 22.19.0" in agents.node_problem()
    monkeypatch.setattr(agents.subprocess, "run", version("v22.19.0\n"))
    assert agents.node_problem() is None
    monkeypatch.setattr(agents.shutil, "which", lambda _: None)
    assert "not on PATH" in agents.node_problem()
