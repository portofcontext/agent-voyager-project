"""Seam tests: avp-anthropic's manifest is consistent across surfaces.

The manifest the agent publishes lives in three places that MUST agree:

  1. `avp_anthropic.manifest()` — the in-process function.
  2. `avp-anthropic describe` — the CLI subcommand, prints JSON to stdout.
  3. `agent_described.data.avp.agent` — the on-wire event the agent
     emits between run_requested and agent_started.

If any of these diverged, a Commission author who introspected the agent
pre-flight (via describe) would see a different surface than what's
recorded in the trajectory at run time, breaking the audit-trail
contract.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

import pytest

from avp_anthropic import cli as cli_module
from avp_anthropic import manifest as build_manifest


def test_manifest_function_returns_valid_agent_manifest() -> None:
    m = build_manifest()
    assert m.agent_name == "avp-anthropic"
    assert m.avp_spec_version == "0.1"
    # Shell tools are the documented runtime built-ins; they MUST appear
    # so a Commission author writing `allowed_tools` can rely on the manifest.
    assert m.built_in_tools is not None
    names = [t.name for t in m.built_in_tools]
    assert {"bash", "read_file", "write_file"} <= set(names)
    # The Anthropic driver brings no built-in subagents or skills — those
    # surfaces come from Commission only. Honest-null here.
    assert m.built_in_subagents is None
    assert m.built_in_skills is None
    assert m.capabilities is not None
    assert "thinking" in m.capabilities


def test_describe_subcommand_prints_manifest_as_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`avp-anthropic describe` MUST print the same JSON the function returns.

    Catches drift if someone hand-edits the CLI to filter or reformat the
    manifest before printing.
    """
    monkeypatch.setattr(cli_module.sys, "stdout", io.StringIO())
    code = cli_module.main(["describe"])
    assert code == 0
    printed = cli_module.sys.stdout.getvalue()
    parsed = json.loads(printed)
    expected = build_manifest().model_dump(by_alias=True, exclude_none=True)
    assert parsed == expected


class _MinimalClient:
    """One-turn stub Anthropic client — enough to exercise the run prelude."""

    def __init__(self) -> None:
        self.messages = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            usage=SimpleNamespace(input_tokens=5, output_tokens=1),
            stop_reason="end_turn",
        )


def test_agent_described_event_payload_equals_manifest_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `agent_described` event the CLI emits MUST carry the same
    manifest payload the standalone `manifest()` function returns.

    Without this seam, a agent could ship a `describe` JSON that says
    one thing and a wire trajectory that says another — and the
    pre-flight introspection contract goes silent.
    """
    real_driver_cls = cli_module.AnthropicModelDriver
    client = _MinimalClient()

    def make_driver(**kwargs: Any):
        kwargs["client"] = client
        return real_driver_cls(**kwargs)

    monkeypatch.setattr(cli_module, "AnthropicModelDriver", make_driver)

    config = {
        "schema_version": "0.1",
        "run_id": "manifest-seam",
        "model": "claude-sonnet-4-6",
        "supervisor": {"name": "test-supervisor"},
    }
    stdin = io.StringIO(json.dumps(config) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(cli_module.sys, "stdin", stdin)
    monkeypatch.setattr(cli_module.sys, "stdout", stdout)

    code = cli_module.main([])
    assert code == 0

    events = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    described = next(e for e in events if e["type"] == "avp.agent_described")
    on_wire = described["data"]["avp.manifest"]
    expected = build_manifest().model_dump(by_alias=True, exclude_none=True)
    assert on_wire == expected
