"""Installing agents (avp releases, custom manifests, local builds) and resolving them, offline.

Release downloads are stubbed at `_resolve_release` / `_download`, serving a
fake release with an `avp-release.json`. Python installs need `uv` + network,
so `avp/scripts/smoke-agent.py` covers them against real builds; binary and
Node installs run end to end here with fake artifacts.
"""

from __future__ import annotations

import io
import json
import tarfile

import pytest

from avp_cli import agent_install, agents, images, release_manifest
from avp_cli.environment import Environment


@pytest.fixture
def avp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    monkeypatch.delenv("AVP_AGENT_REPO", raising=False)
    return tmp_path


def _tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _package(entry: str = "dist/src/main.js") -> bytes:
    """A minimal Node package archive shaped like the pi release asset."""
    return _tar({entry: b"console.log('pi')\n"})


def _node_release(agent: str, version: str, asset: str) -> dict:
    return {
        "schema_version": 1,
        "agent": agent,
        "version": version,
        "kind": "node",
        "node": {
            "version": "22.23.3",
            "min": "22.19.0",
            "asset": asset,
            "entry": "dist/src/main.js",
        },
    }


def _goose_release(version: str = "local") -> dict:
    return {
        "schema_version": 1,
        "agent": "goose",
        "version": version,
        "kind": "binary",
        "setup": ["apt-get install -y libgomp1"],
        "binary": {
            "name": "avp-goose-conformance",
            "asset": "avp-goose-conformance-{target}.tar.gz",
            "gpu_asset": "avp-goose-conformance-vulkan-{target}.tar.gz",
            "gpu_setup": ["apt-get install -y libvulkan1"],
        },
    }


def _manifest(tmp_path, *, container: bool = True):
    d = tmp_path / "my-agent"
    d.mkdir(exist_ok=True)
    body = {"command": ["my-agent"], "cwd": ".", "env": {}}
    if container:
        body["container"] = {"install": ["pip install my-agent"], "command": ["my-agent"]}
    (d / "avp-conformance.json").write_text(json.dumps(body))
    return d / "avp-conformance.json"


def _stub_release(monkeypatch, assets: dict[str, bytes]):
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


def _pi_release(monkeypatch, version: str):
    manifest = _node_release("pi", version, "avp-pi.tar.gz")
    return _stub_release(
        monkeypatch,
        {"avp-release.json": json.dumps(manifest).encode(), "avp-pi.tar.gz": _package()},
    )


def _local_dir(tmp_path, manifest: dict, files: dict[str, bytes]):
    d = tmp_path / f"build-{manifest['agent']}"
    d.mkdir()
    (d / release_manifest.FILENAME).write_text(json.dumps(manifest))
    for name, data in files.items():
        (d / name).write_bytes(data)
    return d


# ── avp releases ──────────────────────────────────────────────────────────────


def test_release_install_pins_the_cli_version_and_records_the_origin(avp_home, monkeypatch) -> None:
    pin = agents.AGENT_SOURCES["pi"].version
    seen = _pi_release(monkeypatch, pin)

    result = agent_install.install("pi")

    assert seen["version"] == pin
    assert seen["repo"] == agents.CANONICAL_REPO
    assert result.source == "release" and result.kind == "node"
    record = agents.installed_record("pi")
    assert record["from"] == "release" and record["agent"] == "pi"
    assert agents.origin_label(record) == f"avp release {pin}"
    assert (avp_home / "agents" / "pi" / release_manifest.FILENAME).is_file()
    resolved = agents.resolve_agent("pi")
    assert resolved.origin == "release" and resolved.agent_name == "avp-pi"
    assert resolved.label is None  # boards keep the descriptor name for releases


def test_release_recipe_follows_its_manifest_from_the_installed_release(
    avp_home, monkeypatch
) -> None:
    monkeypatch.setenv("AVP_AGENT_REPO", "acme/avp-fork")
    _pi_release(monkeypatch, "9.9.9")
    agent_install.install("pi", version="9.9.9")

    resolved = agents.resolve_agent("pi")
    assert resolved.origin_label == "avp release 9.9.9 (fork: acme/avp-fork)"
    recipe = agents.container_recipe(resolved)
    steps = "\n".join(recipe.setup + recipe.install)
    assert "acme/avp-fork/releases/download/agent-pi-v9.9.9/avp-pi.tar.gz" in steps
    assert "node-v22.23.3-linux-" in steps  # the Node the release asked for


def test_per_platform_node_release_picks_the_host_archive(avp_home, monkeypatch) -> None:
    monkeypatch.setattr(agent_install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(agent_install.platform, "machine", lambda: "aarch64")
    pin = agents.AGENT_SOURCES["opencode"].version
    manifest = _node_release("opencode", pin, "avp-opencode-{platform}.tar.gz")
    _stub_release(
        monkeypatch,
        {
            "avp-release.json": json.dumps(manifest).encode(),
            "avp-opencode-linux-arm64.tar.gz": _package(),
            "avp-opencode-linux-x64.tar.gz": b"not an archive",
        },
    )
    result = agent_install.install("opencode")
    assert result.kind == "node" and result.version == pin


def test_release_without_a_manifest_is_refused(avp_home, monkeypatch) -> None:
    _stub_release(monkeypatch, {"avp-pi.tar.gz": _package()})
    with pytest.raises(agent_install.InstallError, match="predates this avp-cli"):
        agent_install.install("pi")
    assert not (avp_home / "agents" / "pi").exists()


def test_release_manifest_must_describe_the_agent_and_version(avp_home, monkeypatch) -> None:
    pin = agents.AGENT_SOURCES["pi"].version
    other = _node_release("gemini-cli", pin, "avp-pi.tar.gz")
    _stub_release(monkeypatch, {"avp-release.json": json.dumps(other).encode()})
    with pytest.raises(agent_install.InstallError, match="describes agent 'gemini-cli'"):
        agent_install.install("pi")
    _pi_release(monkeypatch, "0.0.0")
    with pytest.raises(agent_install.InstallError, match=r"describes pi 0\.0\.0"):
        agent_install.install("pi", version="9.9.9")


def test_binary_release_gpu_recipe_uses_its_variant(avp_home, monkeypatch) -> None:
    pin = agents.AGENT_SOURCES["goose"].version
    host = f"avp-goose-conformance-{agent_install.current_target()}.tar.gz"
    _stub_release(
        monkeypatch,
        {
            "avp-release.json": json.dumps(_goose_release(pin)).encode(),
            host: _tar({"avp-goose-conformance": b"\x7fELF"}),
        },
    )
    agent_install.install("goose")
    resolved = agents.resolve_agent("goose")
    assert (avp_home / "agents" / "goose" / "bin" / "avp-goose-conformance").is_file()

    cpu = agents.container_recipe(resolved)
    gpu = agents.container_recipe(resolved, gpu=True)
    assert "avp-goose-conformance-$(uname -m)-unknown-linux-gnu.tar.gz" in cpu.install[0]
    assert "vulkan-$(uname -m)-unknown-linux-gnu.tar.gz" in gpu.install[0]
    assert "apt-get install -y libvulkan1" in gpu.setup
    assert "apt-get install -y libvulkan1" not in cpu.setup
    assert cpu.command == ("avp-goose-conformance",)


def test_install_all_continues_past_failures(avp_home, monkeypatch) -> None:
    def fake(source, *, version=None, force=False):
        if source.name == "pi":
            raise agent_install.InstallError("`node` is not on PATH")
        d = agent_install._prepare_dir(source.name, force=True)
        v = source.version
        agent_install._write_record(
            d, {"name": source.name, "from": "release", "agent": source.name, "version": v}
        )
        (d / release_manifest.FILENAME).write_text("{}")
        return agent_install.InstallResult(source.name, v, "binary", "release", d)

    monkeypatch.setattr(agent_install, "install_release", fake)
    first = list(agent_install.install_all())
    assert [n for n, _, _ in first] == list(agents.AGENT_SOURCES)
    assert [n for n, _, err in first if err] == ["pi"]

    again = {n: (r, e) for n, r, e in agent_install.install_all()}
    assert again["goose"] == (None, None)  # already at the pinned release: skipped
    assert again["pi"][1] is not None  # still failing, still retried


def test_install_all_replaces_installs_not_at_the_pinned_release(avp_home, monkeypatch) -> None:
    installed = []

    def fake(source, *, version=None, force=False):
        installed.append(source.name)
        return agent_install.InstallResult(
            source.name, source.version, "binary", "release", avp_home
        )

    old = avp_home / "agents" / "goose"
    old.mkdir(parents=True)
    (old / "installed.json").write_text(
        json.dumps({"name": "goose", "from": "release", "agent": "goose", "version": "0.0.1"})
    )
    monkeypatch.setattr(agent_install, "install_release", fake)
    list(agent_install.install_all())
    assert "goose" in installed


def test_not_installed_points_at_install_all(avp_home) -> None:
    with pytest.raises(SystemExit, match="avp agent install --all"):
        agents.resolve_agent("goose")


def test_no_checkout_fallback(avp_home) -> None:
    # Running from a source checkout no longer resolves in-repo manifests.
    assert not agents.is_installed("claude-code")
    with pytest.raises(SystemExit):
        agents.resolve_agent("claude-code")


def test_installs_from_before_release_manifests_ask_for_a_reinstall(avp_home) -> None:
    d = avp_home / "agents" / "pi"
    d.mkdir(parents=True)
    (d / "installed.json").write_text(
        json.dumps({"name": "pi", "version": "0.1.0", "source": "release"})
    )
    (d / "avp-conformance.json").write_text(json.dumps({"command": ["node", "x"], "cwd": "."}))
    resolved = agents.resolve_agent("pi")
    assert resolved.origin == "release" and resolved.origin_label == "avp release 0.1.0"
    assert "avp agent install pi --force" in agents.preflight("pi")
    with pytest.raises(agents.NoContainerRecipe, match="avp agent install pi --force"):
        agents.container_recipe(resolved)


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


def test_local_build_needs_its_own_name(avp_home, tmp_path) -> None:
    d = _local_dir(tmp_path, _node_release("pi", "local", "avp-pi.tar.gz"), {})
    with pytest.raises(agent_install.InstallError, match="--as pi-dev"):
        agent_install.install("pi", from_dir=d)
    with pytest.raises(agent_install.InstallError, match="built-in agent name"):
        agent_install.install("pi", from_dir=d, as_name="goose")
    with pytest.raises(agent_install.InstallError, match="pass --from"):
        agent_install.install("pi", as_name="pi-dev")
    with pytest.raises(agent_install.InstallError, match="--version picks a release"):
        agent_install.install("pi", from_dir=d, as_name="pi-dev", version="1.0.0")


def test_local_build_needs_a_release_manifest_for_the_agent(avp_home, tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(agent_install.InstallError, match=r"no avp-release\.json"):
        agent_install.install("pi", from_dir=empty, as_name="pi-dev")
    other = _local_dir(tmp_path, _goose_release(), {})
    with pytest.raises(agent_install.InstallError, match="describes agent 'goose'"):
        agent_install.install("pi", from_dir=other, as_name="pi-dev")


def test_local_build_is_labeled_and_copied_into_the_image(avp_home, tmp_path) -> None:
    d = _local_dir(
        tmp_path, _node_release("pi", "local", "avp-pi.tar.gz"), {"avp-pi.tar.gz": _package()}
    )
    agent_install.install("pi", from_dir=d, as_name="pi-dev")

    resolved = agents.resolve_agent("pi-dev")
    assert resolved.origin == "local" and resolved.origin_label == "local build of pi"
    assert resolved.agent_name == "avp-pi"  # Commissions keyed for pi still bind
    assert resolved.label == "pi-dev"  # but boards tell it apart
    record = agents.installed_record("pi-dev")
    assert sorted(record["artifacts"]) == ["avp-pi.tar.gz", "avp-release.json"]
    assert record["host"] is True

    recipe = agents.container_recipe(resolved)
    assert recipe.context == str(avp_home / "agents" / "pi-dev" / "artifacts")
    df = images.dockerfile(Environment(), recipe)
    assert "COPY . /opt/avp-artifacts" in df
    assert "cat /opt/avp-artifacts/avp-pi.tar.gz | tar -xz -C /opt/pi" in df
    assert "releases/download" not in df  # not the avp release

    before = images.image_tag(Environment(), recipe)
    (avp_home / "agents" / "pi-dev" / "artifacts" / "avp-pi.tar.gz").write_bytes(b"rebuilt")
    assert images.image_tag(Environment(), recipe) != before  # new artifacts, new image


def test_local_build_without_a_host_artifact_runs_but_cannot_describe(
    avp_home, tmp_path, monkeypatch
) -> None:
    for mod in (agent_install.platform, agents.platform):
        monkeypatch.setattr(mod, "system", lambda: "Darwin")
    monkeypatch.setattr(agent_install.platform, "machine", lambda: "arm64")
    linux = "avp-goose-conformance-aarch64-unknown-linux-gnu.tar.gz"
    d = _local_dir(tmp_path, _goose_release(), {linux: _tar({"avp-goose-conformance": b"x"})})
    agent_install.install("goose", from_dir=d, as_name="goose-dev")

    assert agents.installed_record("goose-dev")["host"] is False
    assert "can't describe here" in agents.preflight("goose-dev")
    recipe = agents.container_recipe(agents.resolve_agent("goose-dev"))
    assert recipe.install == (
        "cat /opt/avp-artifacts/avp-goose-conformance-$(uname -m)-unknown-linux-gnu.tar.gz "
        "| tar -xz -C /usr/local/bin && chmod +x /usr/local/bin/avp-goose-conformance",
    )


def test_node_package_without_the_entry_is_rejected(avp_home, tmp_path) -> None:
    d = _local_dir(
        tmp_path,
        _node_release("pi", "local", "avp-pi.tar.gz"),
        {"avp-pi.tar.gz": _package(entry="other.js")},
    )
    with pytest.raises(agent_install.InstallError, match="did not contain"):
        agent_install.install("pi", from_dir=d, as_name="pi-dev")
    assert not (avp_home / "agents" / "pi-dev").exists()


def test_reinstall_needs_force_and_uninstall(avp_home, tmp_path) -> None:
    d = _local_dir(
        tmp_path, _node_release("pi", "local", "avp-pi.tar.gz"), {"avp-pi.tar.gz": _package()}
    )
    agent_install.install("pi", from_dir=d, as_name="pi-dev")
    with pytest.raises(agent_install.InstallError, match="already installed"):
        agent_install.install("pi", from_dir=d, as_name="pi-dev")
    agent_install.install("pi", from_dir=d, as_name="pi-dev", force=True)
    assert agent_install.uninstall("pi-dev") is True
    assert agent_install.uninstall("pi-dev") is False


# ── host prerequisites ────────────────────────────────────────────────────────


def test_current_target_is_mac_or_linux() -> None:
    assert any(s in agent_install.current_target() for s in ("apple-darwin", "linux-gnu"))


def test_node_preflight_checks_the_runtime_version(monkeypatch) -> None:
    import subprocess

    monkeypatch.setattr(agents.shutil, "which", lambda _: "/usr/bin/node")

    def version(out):
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out)

    monkeypatch.setattr(agents.subprocess, "run", version("v22.17.1\n"))
    assert "needs Node 22.19.0" in agents.node_problem("22.19.0")
    monkeypatch.setattr(agents.subprocess, "run", version("v22.19.0\n"))
    assert agents.node_problem("22.19.0") is None
    monkeypatch.setattr(agents.shutil, "which", lambda _: None)
    assert "not on PATH" in agents.node_problem("22.19.0")
