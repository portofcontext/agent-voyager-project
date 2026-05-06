"""Tests for simple-supervisor-example.

Covers the wire-level supervisor logic that doesn't need a live runner:
  - Profile → Config compilation
  - Trajectory → Summary classification
  - Subprocess wrapper drives the reference aep runner with ScriptedModel
"""

from __future__ import annotations

import sys

import pytest
from simple_supervisor import (
    COST_BOUNDED,
    DDD_STRICT,
    DEV_LOOSE,
    QUALITY_GUARDS,
    Summary,
    build_config,
    render,
    summarize,
)

from aep import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Config,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    StopReason,
    ToolInvokedEvent,
    ToolReturnedEvent,
    VerifierEvaluatedEvent,
)

# ── Profile / Config compilation ──────────────────────────────────────────────


def test_build_config_inherits_quality_guards_profile() -> None:
    """quality-guards is a generic code-quality profile (the no-todos verifier)."""
    cfg = build_config(run_id="r1", prompt="x", profile="quality-guards")
    assert "bash" in cfg.allowed_tools
    assert cfg.boundary.max_cost_usd == 0.50
    assert cfg.boundary.max_steps == 10
    assert {v.name for v in cfg.verifiers} == {"no-todos-in-writes"}


def test_build_config_inherits_ddd_strict_profile() -> None:
    """ddd-strict compiles real DDD concerns: layer purity, aggregate
    invariants (pytest-driven), and ubiquitous language enforcement."""
    cfg = build_config(run_id="r1", prompt="x", profile="ddd-strict")
    assert "bash" in cfg.allowed_tools
    assert cfg.boundary.max_cost_usd == 0.75
    assert cfg.boundary.max_steps == 12
    names = {v.name for v in cfg.verifiers}
    assert names == {
        "domain-layer-purity",
        "aggregate-invariants",
        "no-anemic-suffixes-in-domain",
    }
    # Each verifier maps to a DDD concept with the right on_failure semantics.
    # domain-layer-purity halts (architectural contract violation).
    # aggregate-invariants and no-anemic-suffixes inject_correction so the
    # agent can self-recover — invariants get a stronger nudge that says
    # "don't loosen the invariant; restructure the feature."
    by_name = {v.name: v for v in cfg.verifiers}
    assert by_name["domain-layer-purity"].on_failure.value == "halt"
    assert by_name["aggregate-invariants"].on_failure.value == "inject_correction"
    assert by_name["no-anemic-suffixes-in-domain"].on_failure.value == "inject_correction"
    # The aggregate-invariants correction encodes the DDD principle.
    assert "loosen" in by_name["aggregate-invariants"].correction_message
    assert "invariant" in by_name["aggregate-invariants"].correction_message


def test_build_config_extra_tools_extend_allowed_tools() -> None:
    cfg = build_config(
        run_id="r1",
        prompt="x",
        profile="cost-bounded",
        extra_tools=[
            {
                "name": "lookup_user",
                "description": "demo RPC",
                "input_schema": {"type": "object"},
            },
        ],
    )
    assert "lookup_user" in cfg.allowed_tools
    # The original profile tool is still there
    assert "read_file" in cfg.allowed_tools
    assert cfg.tools[0].name == "lookup_user"


def test_build_config_boundary_overrides_win() -> None:
    cfg = build_config(
        run_id="r1",
        prompt="x",
        profile="dev-loose",
        boundary_overrides={"max_cost_usd": 0.01},
    )
    # Override wins; other fields preserved from profile
    assert cfg.boundary.max_cost_usd == 0.01
    assert cfg.boundary.max_steps == 20


def test_profiles_are_distinct() -> None:
    assert COST_BOUNDED.allowed_tools != DDD_STRICT.allowed_tools
    assert DEV_LOOSE.boundary != COST_BOUNDED.boundary
    # DDD_STRICT and QUALITY_GUARDS share allowed_tools but have different
    # verifiers and different system_prompts (DDD_STRICT carries one).
    assert DDD_STRICT.verifiers != QUALITY_GUARDS.verifiers
    assert DDD_STRICT.system_prompt is not None
    assert QUALITY_GUARDS.system_prompt is None


# ── Trajectory summarization ──────────────────────────────────────────────────


def _make_state(*, cost: float, tokens: int, turns: int) -> dict:
    return {
        "total_cost_usd": cost,
        "total_tokens": tokens,
        "total_turns": turns,
        "started_at": "2026-05-04T18:00:00Z",
        "duration_ms": 1234,
    }


def test_summarize_classifies_three_fact_classes() -> None:
    cfg = Config(schema_version="0.1", run_id="r-summary", model="m")
    events = [
        AgentStartedEvent(run_id="r-summary", model="m"),
        ModelTurnEndedEvent(
            run_id="r-summary",
            step=1,
            tokens_input=10,
            tokens_output=5,
            cost_usd=0.001,
            duration_ms=10,
        ),
        ToolInvokedEvent(run_id="r-summary", step=1, call_id="c1", tool="bash", input={"x": 1}),
        ToolReturnedEvent(
            run_id="r-summary",
            step=1,
            call_id="c1",
            tool="bash",
            output="ok",
            duration_ms=1,
        ),
        VerifierEvaluatedEvent(run_id="r-summary", name="rule-A", passed=True, step=1),
        VerifierEvaluatedEvent(run_id="r-summary", name="rule-B", passed=False, step=1),
        CostRecordedEvent(run_id="r-summary", state=_make_state(cost=0.001, tokens=15, turns=1)),
        AgentStoppedEvent(
            run_id="r-summary",
            reason=StopReason.converged,
            state=_make_state(cost=0.001, tokens=15, turns=1),
            total_tokens=15,
            total_cost_usd=0.001,
            total_turns=1,
            duration_ms=1234,
        ),
    ]
    s = summarize(events)
    assert isinstance(s, Summary)
    assert s.run_id == "r-summary"
    assert s.stop_reason == "converged"
    assert s.total_turns == 1
    assert s.tools["bash"].invocations == 1
    assert s.verifier_pass_count == 1
    assert s.verifier_fail_count == 1
    assert pytest.approx(s.total_cost_usd, abs=1e-9) == 0.001

    rendered = render(s)
    assert "rule-A" in rendered
    assert "rule-B" in rendered
    assert "FAIL" in rendered  # the failing verifier shows up
    assert "PASS" in rendered  # the passing one too
    assert "bash: 1 call" in rendered


# ── Subprocess wrapper end-to-end (uses no LLM — pipes to a tiny scripted runner) ──


_INLINE_SCRIPTED_RUNNER = """\
import json, sys
from aep import Config, write_event
from aep.runner import AEPRunner
from aep.runner.mock import ScriptedTools, ScriptedSupervisor, parse_scripted_model

cfg_line = sys.stdin.readline()
cfg = Config.model_validate(json.loads(cfg_line))

# Two-turn scripted run: turn 1 calls 'bash', turn 2 converges.
model = parse_scripted_model([
    {
        "tokens_input": 50, "tokens_output": 10, "cost_usd": 0.001, "duration_ms": 1,
        "text": "running bash",
        "tool_calls": [{"call_id": "c1", "tool": "bash", "input": {"cmd": "echo hi"}}],
        "converged": False,
    },
    {
        "tokens_input": 10, "tokens_output": 5, "cost_usd": 0.0005, "duration_ms": 1,
        "text": "all done", "converged": True,
    },
])
tools = ScriptedTools({"bash": {"output": "hi", "duration_ms": 1}})

# Streaming supervisor: every observed event gets written to stdout as NDJSON.
class _StreamingSupervisor(ScriptedSupervisor):
    def observe(self, event):
        super().observe(event)
        write_event(event, file=sys.stdout)

runner = AEPRunner(
    config=cfg,
    model=model,
    tools=tools,
    supervisor=_StreamingSupervisor([]),
)
runner.run()
"""


def test_run_subprocess_drives_a_real_runner_end_to_end(tmp_path) -> None:
    """Spawn a tiny inline runner that uses ScriptedModel + ScriptedTools, pipe a
    Config in, parse events out. Pins the wire-level supervisor flow."""
    from simple_supervisor import run_subprocess

    runner_script = tmp_path / "tiny_runner.py"
    runner_script.write_text(_INLINE_SCRIPTED_RUNNER)

    cfg = build_config(
        run_id="subprocess-smoke",
        prompt="anything",
        profile="dev-loose",
        boundary_overrides={"max_steps": 5},
    )
    # Strip verifiers — the dev-loose profile's verifier shells out to `true`,
    # but on a subprocess driven by ScriptedModel we don't want shell calls
    # interleaving with the test.
    cfg = cfg.model_copy(update={"verifiers": None})

    events = run_subprocess(
        [sys.executable, str(runner_script)],
        cfg,
        timeout_s=10.0,
    )

    types = [getattr(ev, "type", None) for ev in events if hasattr(ev, "type")]
    assert "agent_started" in types
    assert "model_turn_started" in types
    assert "tool_invoked" in types
    assert "tool_returned" in types
    assert "agent_stopped" in types

    s = summarize(events)
    assert s.stop_reason == "converged"
    assert s.tools["bash"].invocations == 1
    assert s.total_turns == 2
