"""Seam tests: avp-claude-agent's manifest is consistent across surfaces.

The manifest the agent publishes lives in three places that MUST agree:

  1. `avp_claude_agent.manifest()` — the in-process function.
  2. `avp-claude-agent describe` — the CLI subcommand, prints JSON.
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
from typing import Any

import pytest

from avp import AgentDescribedEvent, Commission, RunRequestedEvent
from avp_claude_agent import (
    CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS,
    CLAUDE_CODE_PRESET_TOOLS,
    ClaudeAgentTranslator,
)
from avp_claude_agent import cli as cli_module
from avp_claude_agent import (
    manifest as build_manifest,
)


def test_manifest_function_returns_valid_agent_manifest() -> None:
    m = build_manifest()
    assert m.agent_name == "avp-claude-agent"
    assert m.avp_spec_version == "0.1"
    # Built-in tools mirror the documented Claude Code preset — the audit
    # trail otherwise wouldn't list what `claude_code` actually exposes.
    assert m.built_in_tools is not None
    assert {t.name for t in m.built_in_tools} == set(CLAUDE_CODE_PRESET_TOOLS)
    # general-purpose is the SDK's only runtime-bundled subagent. The
    # manifest snapshots from the documented surface.
    assert m.built_in_subagents is not None
    assert {sa.name for sa in m.built_in_subagents} == set(CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS)
    # SDK does not bundle skills programmatically — null is honest.
    assert m.built_in_skills is None
    assert m.capabilities is not None
    for cap in ("mcp", "subagents", "skills", "thinking"):
        assert cap in m.capabilities


def test_describe_subcommand_prints_manifest_as_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`avp-claude-agent describe` MUST print the same JSON `manifest()` returns."""
    monkeypatch.setattr(cli_module.sys, "stdout", io.StringIO())
    code = cli_module.main(["describe"])
    assert code == 0
    printed = cli_module.sys.stdout.getvalue()
    parsed = json.loads(printed)
    expected = build_manifest().model_dump(by_alias=True, exclude_none=True)
    assert parsed == expected


def test_translator_emits_run_prelude_when_manifest_supplied() -> None:
    """When a manifest is passed, the translator opens the trajectory with
    run_requested → agent_described — even with a no-op SDK fake. The
    agent_described event's payload MUST equal the supplied manifest.
    """
    cfg = Commission.model_validate(
        {
            "schema_version": "0.1",
            "run_id": "manifest-seam",
            "model": "claude-sonnet-4-6",
            "prompt": "hello",
            "supervisor": {"name": "test-supervisor"},
        }
    )
    out: list[Any] = []
    manifest = build_manifest()
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        manifest=manifest,
    )
    t._emit_run_prelude()

    assert isinstance(out[0], RunRequestedEvent)
    assert out[0].source == "avp://supervisor"
    assert out[0].data.avp_supervisor_name == "test-supervisor"
    assert out[0].data.avp_config["run_id"] == "manifest-seam"

    assert isinstance(out[1], AgentDescribedEvent)
    assert out[1].source == "avp://agent"
    on_wire = out[1].data.avp_agent.model_dump(by_alias=True, exclude_none=True)
    expected = manifest.model_dump(by_alias=True, exclude_none=True)
    assert on_wire == expected


def test_translator_skips_prelude_in_delegated_mode() -> None:
    """Delegated mode (suppress_lifecycle=True) means the parent tracer
    owns the lifecycle bookends and prelude. Emitting prelude here would
    duplicate run_requested + agent_described under the same trace_id —
    which consumers cannot reconcile.
    """
    cfg = Commission.model_validate(
        {"schema_version": "0.1", "run_id": "delegated", "supervisor": {"name": "x"}}
    )
    out: list[Any] = []
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        manifest=build_manifest(),
        suppress_lifecycle=True,
    )
    t._emit_run_prelude()
    assert out == []


def test_translator_skips_prelude_when_no_manifest() -> None:
    """Translator constructed without a manifest (in-process embedded use)
    MUST NOT emit prelude. The wire only opens with run_requested when
    the agent identifies itself.
    """
    cfg = Commission.model_validate({"schema_version": "0.1", "run_id": "no-manifest"})
    out: list[Any] = []
    t = ClaudeAgentTranslator(cfg, on_event=out.append)
    t._emit_run_prelude()
    assert out == []
