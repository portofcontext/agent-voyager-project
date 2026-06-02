"""Sandbox confinement: the `--sandbox` mode resolution, the srt settings the
CLI generates, and that run_agent wraps the command only when asked."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from avp_cli import sandbox

# ── decide(mode) ──────────────────────────────────────────────────────────────


def test_off_never_sandboxes() -> None:
    assert sandbox.decide("off") == (False, None)


def test_auto_sandboxes_when_srt_present(monkeypatch) -> None:
    monkeypatch.setattr(sandbox, "available", lambda: True)
    enabled, note = sandbox.decide("auto")
    assert enabled is True and "srt" in note


def test_auto_runs_unsandboxed_when_srt_absent(monkeypatch) -> None:
    # The onboarding contract: no srt → no error, just run and say so.
    monkeypatch.setattr(sandbox, "available", lambda: False)
    enabled, note = sandbox.decide("auto")
    assert enabled is False and "npm install -g @anthropic-ai/sandbox-runtime" in note


def test_on_requires_srt(monkeypatch) -> None:
    monkeypatch.setattr(sandbox, "available", lambda: True)
    assert sandbox.decide("on") == (True, "runs are sandboxed via srt")
    monkeypatch.setattr(sandbox, "available", lambda: False)
    with pytest.raises(sandbox.SandboxUnavailable, match="npm install"):
        sandbox.decide("on")


# ── settings_file ───────────────────────────────────────────────────────────


def test_settings_seeds_network_and_write_allowlist(tmp_path) -> None:
    p = sandbox.settings_file(
        tmp_path, write_paths=["/work/out", "/work/out"], allow_domains=["x.test"]
    )
    prof = json.loads(p.read_text())
    # writes: deduped, exactly what we passed (deny-by-default everywhere else)
    assert prof["filesystem"]["allowWrite"] == ["/work/out"]
    # network: the model-provider defaults plus the extra, and the provider API is in
    assert "api.anthropic.com" in prof["network"]["allowedDomains"]
    assert "x.test" in prof["network"]["allowedDomains"]
    # credential stores stay unreadable
    assert "~/.ssh" in prof["filesystem"]["denyRead"]


def test_settings_allows_macos_trust_lookup_on_darwin(tmp_path) -> None:
    prof = json.loads(sandbox.settings_file(tmp_path, write_paths=["/tmp"]).read_text())
    if sys.platform == "darwin":
        assert prof["network"]["allowMachLookup"] == ["com.apple.trustd.agent"]
    else:
        assert "allowMachLookup" not in prof["network"]


# ── run_agent wiring (no srt needed: the prefix builder is stubbed) ───────────


def test_run_agent_wraps_only_when_sandboxed(tmp_path, monkeypatch) -> None:
    from avp_conformance.manifest import AgentManifest

    from avp.commission import Commission
    from avp_cli import agent as agent_mod

    captured: dict[str, list[str]] = {}

    def fake_blocking(cmd, cwd, env, timeout_s):
        captured["cmd"] = cmd
        Path(cmd[cmd.index("--out") + 1]).write_text("")  # agent "wrote" an empty trajectory
        return None

    monkeypatch.setattr(agent_mod, "_run_blocking", fake_blocking)
    monkeypatch.setattr(agent_mod.sandbox_mod, "prefix", lambda _settings: ["SRT", "--"])

    manifest = AgentManifest(command=["my-agent"], cwd=".", env={})
    commission = Commission(schema_version="0.1", run_id="r", prompt="hi")
    out = tmp_path / "t.ndjson"

    agent_mod.run_agent(manifest, tmp_path, commission, out_path=out, sandbox=False)
    assert captured["cmd"][0] == "my-agent"  # unsandboxed: command runs as-is

    agent_mod.run_agent(manifest, tmp_path, commission, out_path=out, sandbox=True)
    assert captured["cmd"][:2] == ["SRT", "--"]  # sandboxed: srt prefix prepended
    assert "my-agent" in captured["cmd"]
