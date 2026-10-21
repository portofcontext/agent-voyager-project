"""Every in-tree agent ships: registered, released, and installable.

An adapter under `agents/` that conformance covers but `avp agent install`
can't fetch is only half added; these checks make the release half part of
adding one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from avp_cli.agents import AGENT_SOURCES

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = sorted(
    p.relative_to(ROOT).as_posix()
    for p in ROOT.glob("agents/*/*/avp-conformance.json")
    if p.parts[-3] != "_template"
)


def test_every_in_tree_agent_is_registered() -> None:
    registered = {s.dev_manifest for s in AGENT_SOURCES.values()}
    missing = [m for m in MANIFESTS if m not in registered]
    assert not missing, f"add these to agents.json (agents/_template/README.md §6): {missing}"


@pytest.mark.parametrize("name", sorted(AGENT_SOURCES))
def test_every_registered_agent_has_a_release(name: str) -> None:
    source = AGENT_SOURCES[name]
    assert (ROOT / source.dev_manifest).is_file()
    workflow = ROOT / ".github" / "workflows" / f"release-{name}.yml"
    assert f'tags: ["{source.tag_prefix}-v*"]' in workflow.read_text()
    assert f"agent: {name}" in workflow.read_text()  # publishes via agent-release.yml


def test_the_registry_pins_each_agents_package_version() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "avp" / "scripts" / "agent-pins.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
