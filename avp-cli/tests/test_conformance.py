"""Conformance cases' Commissions and checks, without a sandbox. test_agent.py
runs a case against a real agent."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avp.commission import Model
from avp.descriptor import AgentDescriptor
from avp_cli.cli import app
from avp_cli.conformance import check
from avp_cli.conformance.cases import CASES, Context, Run
from avp_cli.conformance.rules import RULES

DESCRIPTOR = AgentDescriptor(avp_version="0.1", agent_name="pd", agent_version="1.0.0")
CONTEXT = Context(descriptor=DESCRIPTOR, model=check.model("anthropic/claude-haiku-4-5"))
[AGENTS_WITHOUT_ENTRY] = [c for c in CASES if c.name == "agents-without-entry"]


def event(n: int, type: str, data: dict) -> dict:
    return {
        "avp_version": "0.1",
        "id": str(n),
        "type": type,
        "time": "2026-01-01T00:00:00Z",
        "run_id": "r",
        "data": data,
    }


def trajectory(tmp_path: Path, *events: dict | str) -> Path:
    path = tmp_path / "trajectory.ndjson"
    path.write_text("\n".join(e if isinstance(e, str) else json.dumps(e) for e in events) + "\n")
    return path


def run_of(tmp_path: Path, *events: dict | str) -> tuple[Run, list[str]]:
    parsed, types, problems = check.read(trajectory(tmp_path, *events))
    return Run(events=parsed, types=types, exit_code=0), problems


REQUESTED = event(1, "run_requested", {})
DESCRIBED = event(2, "agent_described", {"descriptor": DESCRIPTOR.model_dump(exclude_none=True)})


def test_every_case_names_a_known_rule_and_a_unique_name() -> None:
    assert all(c.rule in RULES for c in CASES)
    assert len({c.name for c in CASES}) == len(CASES)


def test_agents_without_entry_names_another_agent() -> None:
    commission = AGENTS_WITHOUT_ENTRY.commission(CONTEXT)
    assert commission.agents is not None
    assert DESCRIPTOR.agent_name not in commission.agents
    assert commission.model.credential is not None


def test_refusal_passes(tmp_path: Path) -> None:
    error = event(3, "error_occurred", {"error_code": "invalid_commission", "error_message": "x"})
    run, problems = run_of(tmp_path, REQUESTED, DESCRIBED, error)
    assert problems == []
    assert AGENTS_WITHOUT_ENTRY.check(run) == []


@pytest.mark.parametrize(
    ("events", "problem"),
    [
        (
            [REQUESTED, DESCRIBED, event(3, "agent_started", {"prompt": "x"})],
            "the events are run_requested, agent_described, agent_started",
        ),
        (
            [
                REQUESTED,
                DESCRIBED,
                event(3, "error_occurred", {"error_code": "agent_crash", "error_message": "x"}),
            ],
            "error_occurred has the code agent_crash",
        ),
        (
            [
                REQUESTED,
                event(
                    2, "error_occurred", {"error_code": "invalid_commission", "error_message": "x"}
                ),
            ],
            "the events are run_requested, error_occurred",
        ),
    ],
)
def test_refusal_fails(tmp_path: Path, events: list[dict], problem: str) -> None:
    parsed, types, _ = check.read(trajectory(tmp_path, *events))
    [found] = AGENTS_WITHOUT_ENTRY.check(Run(events=parsed, types=types, exit_code=0))
    assert found.startswith(problem)


def test_read_reports_invalid_lines_and_keeps_unknown_types(tmp_path: Path) -> None:
    events, types, problems = check.read(
        trajectory(tmp_path, REQUESTED, "not json", event(3, "from_the_future", {}))
    )
    assert types == ["run_requested", "?", "from_the_future"]
    assert [e is not None for e in events] == [True, False, False]
    [problem] = problems
    assert problem.startswith("line 2 isn't JSON")


def test_read_without_a_trajectory(tmp_path: Path) -> None:
    assert check.read(tmp_path / "missing.ndjson") == ([], [], ["the agent wrote no Trajectory"])


def test_model_must_be_provider_slash_id() -> None:
    assert check.model("openai/gpt-5-mini") == Model(
        provider="openai", id="gpt-5-mini", credential={"env": check.KEY}
    )
    with pytest.raises(Exception, match="isn't provider/model"):
        check.model("gpt-5-mini")


def test_list_shows_each_rule_and_its_cases() -> None:
    result = CliRunner().invoke(app, ["conformance", "list", "--rule", "commission.5.1"])
    assert result.exit_code == 0, result.output
    assert "agents-without-entry" in result.output
    assert "trajectory.4.5" not in result.output


def test_unknown_rule_fails() -> None:
    result = CliRunner().invoke(app, ["conformance", "check", "--agent", "pd", "--rule", "x.1"])
    assert result.exit_code == 1
    assert "no rule x.1" in str(result.exception)
