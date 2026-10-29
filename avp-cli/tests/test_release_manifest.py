"""Release manifests: what each agent declares, and the image recipe it becomes.

The per-agent tests generate every registered agent's `avp-release.json` from
its package metadata (as the release workflows do, over placeholder artifacts)
and check the recipe a sandbox image would be built from.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from avp_cli import images, release_manifest
from avp_cli.agents import AGENT_SOURCES
from avp_cli.environment import Environment
from avp_cli.release_manifest import ReleaseManifest

ROOT = Path(__file__).resolve().parents[2]
URL = "https://example.test/releases/download/agent-x-v1.0.0"


def _script():
    """avp/scripts/release-manifest.py, importable (its sibling helpers too)."""
    scripts = str(ROOT / "avp" / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(
        "release_manifest_script", f"{scripts}/release-manifest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generated(agent: str, out: Path) -> ReleaseManifest:
    """The manifest the release workflow would write for `agent`, over
    placeholder artifacts named like the real ones."""
    script = _script()
    pkg = script.agent_packages.read(agent)
    meta = pkg.meta
    if pkg.kind == "python":
        for dist in meta["wheels"]:
            version = pkg.version if dist == meta["wheels"][-1] else "0.0.0"
            (out / f"{dist.replace('-', '_')}-{version}-py3-none-any.whl").write_bytes(b"")
    elif pkg.kind == "node":
        (out / meta["asset"].replace("{platform}", "linux-x64")).write_bytes(b"")
    else:
        (out / meta["asset"].replace("{target}", "x86_64-unknown-linux-gnu")).write_bytes(b"")
    return ReleaseManifest.model_validate(script.manifest(agent, out))


@pytest.mark.parametrize("agent", sorted(AGENT_SOURCES))
def test_every_agent_generates_a_valid_manifest(agent: str, tmp_path) -> None:
    m = _generated(agent, tmp_path)
    assert m.agent == agent and m.version == AGENT_SOURCES[agent].version
    recipe = release_manifest.container_recipe(m, url=URL)
    assert recipe.command and recipe.install
    if m.python is not None:
        lock = (tmp_path / "requirements.txt").read_text()
        assert "--hash=sha256:" in lock
        pinned = {line.split("==")[0] for line in lock.splitlines() if "==" in line}
        assert "agent-voyager-project" not in pinned  # in-repo wheels ship as files


def test_claude_code_pins_its_cli_and_runs_as_a_sandbox(tmp_path) -> None:
    m = _generated("claude-code", tmp_path)
    recipe = release_manifest.container_recipe(m, url=URL)
    assert ("IS_SANDBOX", "1") in recipe.env
    assert any("@anthropic-ai/claude-code@" in step for step in recipe.setup)
    assert "avp_conformance-0.0.0-py3-none-any.whl" in m.python.wheels


def test_pydantic_ai_locks_anthropic_below_2(tmp_path) -> None:
    _generated("pydantic-ai", tmp_path)
    lock = (tmp_path / "requirements.txt").read_text()
    (line,) = [x for x in lock.splitlines() if x.startswith("anthropic==")]
    assert int(line.split("==")[1].split(".")[0]) < 2


def test_opencode_installs_ripgrep_and_its_arch_archive(tmp_path) -> None:
    m = _generated("opencode", tmp_path)
    recipe = release_manifest.container_recipe(m, url=URL)
    assert any("ripgrep" in step for step in recipe.setup)
    assert f"{URL}/avp-opencode-linux-$(uname -m | sed" in recipe.install[0]
    assert m.node.min == "22.19.0"


# ── recipes ───────────────────────────────────────────────────────────────────


def _python() -> ReleaseManifest:
    return ReleaseManifest.model_validate(
        {
            "schema_version": 1,
            "agent": "pydantic-ai",
            "version": "1.0.0",
            "kind": "python",
            "setup": ["apt-get install -y git"],
            "env": {"A": "1"},
            "python": {
                "module": "avp_pydantic_ai.conformance",
                "wheels": ["lib-0.2.0-py3-none-any.whl", "agent-1.0.0-py3-none-any.whl"],
                "requirements": "requirements.txt",
            },
        }
    )


def test_python_recipe_installs_the_lock_then_the_wheels_without_resolving() -> None:
    recipe = release_manifest.container_recipe(_python(), url=URL)
    assert recipe.setup == ("apt-get install -y git",)
    assert recipe.install == (
        f"pip install --no-cache-dir --require-hashes -r {URL}/requirements.txt",
        f"pip install --no-cache-dir --no-deps {URL}/lib-0.2.0-py3-none-any.whl "
        f"{URL}/agent-1.0.0-py3-none-any.whl",
    )
    assert recipe.command == ("python", "-m", "avp_pydantic_ai.conformance")
    assert recipe.env == (("A", "1"),)
    assert recipe.copy == () and recipe.context is None


def test_local_recipe_copies_the_artifacts_after_setup(tmp_path) -> None:
    recipe = release_manifest.container_recipe(_python(), artifacts=tmp_path)
    df = images.dockerfile(Environment(), recipe)
    assert df.index("apt-get install -y git") < df.index("COPY . /opt/avp-artifacts")
    assert "-r /opt/avp-artifacts/requirements.txt" in df
    assert recipe.context == str(tmp_path)


def test_recipe_takes_exactly_one_source(tmp_path) -> None:
    with pytest.raises(ValueError):
        release_manifest.container_recipe(_python())
    with pytest.raises(ValueError):
        release_manifest.container_recipe(_python(), url=URL, artifacts=tmp_path)


def test_manifest_needs_the_block_for_its_kind(tmp_path) -> None:
    path = tmp_path / release_manifest.FILENAME
    path.write_text('{"schema_version": 1, "agent": "pi", "version": "1", "kind": "node"}')
    with pytest.raises(release_manifest.ManifestError, match="needs a `node` block"):
        release_manifest.load(path)
    with pytest.raises(release_manifest.ManifestError, match=r"no avp-release\.json"):
        release_manifest.load(tmp_path / "missing" / release_manifest.FILENAME)
