"""Installing agents + the resolution order, all offline.

Binary install + resolution are exercised end to end with a fake executable.
The Python (venv) install path needs `uv` + network, so it's covered by the
manual smoke in the PR, not here; we still test its offline guard rails.
"""

from __future__ import annotations

import json

import pytest

from avp_cli import agent_install, agents


@pytest.fixture
def avp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_binary(tmp_path):
    p = tmp_path / "fake-goose"
    p.write_text("#!/bin/sh\necho fake\n")
    p.chmod(0o755)
    return p


def _no_dev_fallback(monkeypatch, tmp_path):
    """Point _repo_root at an empty dir so no in-repo manifest is found."""
    empty = tmp_path / "norepo"
    empty.mkdir()
    monkeypatch.setattr(agents, "_repo_root", lambda: empty)


# ── local binary install ──────────────────────────────────────────────────────


def test_install_local_binary_writes_manifest_and_provenance(avp_home, fake_binary) -> None:
    result = agent_install.install("goose", binary=fake_binary)
    assert result.kind == "binary" and result.source == "local"

    d = avp_home / "agents" / "goose"
    installed_bin = d / "bin" / "avp-goose-conformance"
    assert installed_bin.is_file()
    manifest = json.loads((d / "avp-conformance.json").read_text())
    assert manifest["command"] == [str(installed_bin)]
    assert manifest["cwd"] == "."
    record = json.loads((d / "installed.json").read_text())
    assert record["name"] == "goose" and record["kind"] == "binary"


def test_installed_agent_wins_over_dev_fallback(avp_home, fake_binary) -> None:
    # Even from a checkout (dev fallback present), an installed agent is used.
    agent_install.install("goose", binary=fake_binary)
    resolved = agents.resolve_agent("goose")
    assert resolved.manifest.command == [
        str(avp_home / "agents" / "goose" / "bin" / "avp-goose-conformance")
    ]
    assert "cargo" not in resolved.manifest.command[0]  # not the build-from-source fallback


def test_reinstall_needs_force(avp_home, fake_binary) -> None:
    agent_install.install("goose", binary=fake_binary)
    with pytest.raises(agent_install.InstallError, match="already installed"):
        agent_install.install("goose", binary=fake_binary)
    # --force replaces it cleanly.
    agent_install.install("goose", binary=fake_binary, force=True)


def test_uninstall(avp_home, fake_binary) -> None:
    agent_install.install("goose", binary=fake_binary)
    assert agent_install.uninstall("goose") is True
    assert agent_install.installed_info("goose") is None
    assert agent_install.uninstall("goose") is False  # already gone


# ── resolution order ──────────────────────────────────────────────────────────


def test_explicit_manifest_path_resolves(avp_home, tmp_path) -> None:
    mdir = tmp_path / "third-party"
    mdir.mkdir()
    (mdir / "avp-conformance.json").write_text(
        json.dumps({"command": ["my-agent"], "cwd": ".", "env": {}})
    )
    resolved = agents.resolve_agent(str(mdir / "avp-conformance.json"))
    assert resolved.manifest.command == ["my-agent"]
    assert resolved.name == "third-party"


def test_not_installed_and_no_checkout_errors(avp_home, tmp_path, monkeypatch) -> None:
    _no_dev_fallback(monkeypatch, tmp_path)
    assert not agents.is_installed("goose")
    assert not agents.has_dev_fallback("goose")
    with pytest.raises(SystemExit, match="avp agent install goose"):
        agents.resolve_agent("goose")


# ── guard rails ───────────────────────────────────────────────────────────────


def test_unknown_agent_rejected(avp_home) -> None:
    with pytest.raises(agent_install.InstallError, match="unknown agent"):
        agent_install.install("nope", binary="/x")


def test_wrong_artifact_kind_rejected(avp_home, fake_binary) -> None:
    with pytest.raises(agent_install.InstallError, match="--wheel applies to python"):
        agent_install.install("goose", wheels=["/x.whl"])
    with pytest.raises(agent_install.InstallError, match="--binary applies to binary"):
        agent_install.install("claude-code", binary=fake_binary)


def test_missing_binary_file_rejected(avp_home, tmp_path) -> None:
    with pytest.raises(agent_install.InstallError, match="binary not found"):
        agent_install.install("goose", binary=tmp_path / "does-not-exist")


def test_current_target_is_mac_or_linux() -> None:
    assert any(s in agent_install.current_target() for s in ("apple-darwin", "linux-gnu"))


# ── local node install ────────────────────────────────────────────────────────


def _package(tmp_path, *, entry: str = "dist/src/main.js"):
    """A minimal Node package archive shaped like the pi release asset."""
    import tarfile

    root = tmp_path / "pkg"
    script = root / entry
    script.parent.mkdir(parents=True)
    script.write_text("console.log('pi')\n")
    archive = tmp_path / "avp-pi.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname=".")
    return archive


def test_install_local_node_extracts_and_runs_the_entry_with_node(avp_home, tmp_path) -> None:
    result = agent_install.install("pi", package=_package(tmp_path))
    assert result.kind == "node" and result.source == "local"

    d = avp_home / "agents" / "pi"
    entry = d / "app" / "dist" / "src" / "main.js"
    assert entry.is_file()
    manifest = json.loads((d / "avp-conformance.json").read_text())
    assert manifest["command"] == ["node", str(entry)]
    assert json.loads((d / "installed.json").read_text())["kind"] == "node"
    assert agents.resolve_agent("pi").agent_name == "avp-pi"


def test_node_package_without_the_entry_is_rejected(avp_home, tmp_path) -> None:
    with pytest.raises(agent_install.InstallError, match="did not contain"):
        agent_install.install("pi", package=_package(tmp_path, entry="other.js"))
    assert not (avp_home / "agents" / "pi").exists()


def test_package_flag_applies_only_to_node_agents(avp_home, tmp_path) -> None:
    with pytest.raises(agent_install.InstallError, match="--package applies to node"):
        agent_install.install("goose", package=_package(tmp_path))
    with pytest.raises(agent_install.InstallError, match="--binary applies to binary"):
        agent_install.install("pi", binary=tmp_path / "x")


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
