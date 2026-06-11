"""`describe_agent` — the host-side pre-flight probe must be hermetic.

Agent frameworks sweep $HOME-anchored dirs for ambient state (~/.claude/skills,
~/.agents/skills); runs execute in a sandbox where none of that exists, so the
descriptor must list only what the agent intrinsically ships. These tests
spawn a fake `describe`-contract agent that records its environment and assert
the scrub at the seam.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

from avp_conformance.manifest import AgentManifest

from avp_cli.agent import describe_agent

_SCRUBBED = ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME")


def _fake_agent(tmp_path: Path, envdump: Path, env: dict[str, str]) -> AgentManifest:
    """An agent honoring `describe --out <file>` that dumps the env it saw and
    writes a minimal valid descriptor."""
    script = tmp_path / "fake_agent.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import json, os, sys

            out = sys.argv[sys.argv.index("--out") + 1]
            keep = (
                "HOME", "USERPROFILE", "PATH",
                "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME",
                "AVP_TEST_PASSTHROUGH", "AVP_TEST_MANIFEST",
            )
            json.dump(
                {{k: os.environ.get(k) for k in keep}},
                open({str(envdump)!r}, "w"),
            )
            json.dump(
                {{"agent_name": "fake", "agent_version": "0.0.0", "spec_version": "0.1"}},
                open(out, "w"),
            )
            """
        )
    )
    return AgentManifest(command=[sys.executable, str(script)], cwd=".", env=env)


def test_probe_gets_a_throwaway_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("AVP_TEST_PASSTHROUGH", "still-here")
    envdump = tmp_path / "env.json"

    descriptor, err = describe_agent(
        _fake_agent(tmp_path, envdump, env={"AVP_TEST_MANIFEST": "from-manifest"}), tmp_path
    )

    assert err is None
    assert descriptor is not None and descriptor.agent_name == "fake"

    seen = json.loads(envdump.read_text())
    # The probe's home is a throwaway, never the operator's.
    assert seen["HOME"] != os.environ.get("HOME")
    assert seen["USERPROFILE"] == seen["HOME"]
    # Home-relative XDG overrides are dropped so defaults resolve under the
    # throwaway home.
    for var in _SCRUBBED:
        assert seen[var] is None, f"{var} leaked into the probe"
    # Everything else passes through; manifest env is applied on top.
    assert seen["PATH"] == os.environ.get("PATH")
    assert seen["AVP_TEST_PASSTHROUGH"] == "still-here"
    assert seen["AVP_TEST_MANIFEST"] == "from-manifest"


def test_manifest_env_wins_over_the_scrub(tmp_path):
    envdump = tmp_path / "env.json"
    pinned_home = str(tmp_path / "pinned-home")

    descriptor, err = describe_agent(
        _fake_agent(tmp_path, envdump, env={"HOME": pinned_home}), tmp_path
    )

    assert err is None
    assert descriptor is not None
    assert json.loads(envdump.read_text())["HOME"] == pinned_home
