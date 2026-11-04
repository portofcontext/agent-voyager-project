"""Conformance through the eval engine, with `dispatch` faked to write a saved
Trajectory, so no sandbox starts. test_agent.py runs a case against a real agent."""

import json
from pathlib import Path

import pytest
from conftest import DESCRIPTOR, event, no_sandbox
from typer.testing import CliRunner

from avp.commission import Commission
from avp_cli import paths
from avp_cli.agents import store
from avp_cli.cli import app
from avp_cli.conformance import check, cli
from avp_cli.conformance.cases import CASES, RUN_ID, Case, Context, Skip
from avp_cli.conformance.rules import RULES
from avp_cli.console import Failed
from avp_cli.eval import engine
from avp_cli.eval.scoring import Run
from avp_cli.runs.dispatch import Finished, Options

MODEL = check.model("anthropic/claude-haiku-4-5")
CONTEXT = Context(descriptor=DESCRIPTOR, model=MODEL)
[AGENTS_WITHOUT_ENTRY] = [c for c in CASES if c.name == "agents-without-entry"]

REQUESTED = event(1, "run_requested", {})
DESCRIBED = event(2, "agent_described", {"descriptor": DESCRIPTOR.model_dump(exclude_none=True)})
REFUSED = event(3, "error_occurred", {"error_code": "invalid_commission", "error_message": "x"})
REFUSAL = [REQUESTED, DESCRIBED, REFUSED]


class FakeDispatch:
    """Writes `lines` as each run's Trajectory, or raises `error`."""

    def __init__(self) -> None:
        self.lines: list[dict | str] | None = [*REFUSAL]
        self.exit_code = 0
        self.error: Failed | None = None
        self.commissions: list[Commission] = []
        self.options: list[Options] = []

    def __call__(
        self, agent: store.Agent, entrypoint: list[str], commission: Commission, options: Options
    ) -> Finished:
        self.commissions.append(commission)
        self.options.append(options)
        if self.error:
            raise self.error
        assert options.directory is not None
        options.directory.mkdir(parents=True)
        if self.lines is not None:
            text = "\n".join(e if isinstance(e, str) else json.dumps(e) for e in self.lines)
            (options.directory / paths.TRAJECTORY).write_text(text + "\n")
        return Finished(options.directory, self.exit_code, "")


@pytest.fixture(autouse=True)
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeDispatch:
    monkeypatch.setenv("AVP_HOME", str(tmp_path / "home"))
    fake = FakeDispatch()
    no_sandbox(monkeypatch)
    monkeypatch.setattr(engine, "dispatch", fake)
    return fake


def case(name: str = "a-case", level: str = "MUST", **change: object) -> Case:
    fields: dict = {
        "name": name,
        "rule": "commission.5.1",
        "level": level,
        "about": "x",
        "commission": lambda context: Commission(
            avp_version="0.1", run_id=RUN_ID, model=context.model, prompt="Say hello."
        ),
        "check": lambda run: [],
        **change,
    }
    return Case(**fields)


def test_every_case_names_a_known_rule_and_a_unique_name() -> None:
    assert all(c.rule in RULES for c in CASES)
    assert len({c.name for c in CASES}) == len(CASES)


def test_agents_without_entry_names_another_agent() -> None:
    commission = AGENTS_WITHOUT_ENTRY.commission(CONTEXT)
    assert commission.agents is not None
    assert DESCRIPTOR.agent_name not in commission.agents
    assert commission.model.credential is not None


def test_a_refusal_passes() -> None:
    [outcome] = check.check("pd", [AGENTS_WITHOUT_ENTRY], MODEL)
    assert (outcome.status, outcome.reasons) == ("pass", [])
    assert outcome.run_directory is not None
    assert (outcome.run_directory / paths.TRAJECTORY).is_file()
    assert outcome.run_directory.is_relative_to(paths.conformance())


@pytest.mark.parametrize(
    ("lines", "problem"),
    [
        (
            [REQUESTED, DESCRIBED, event(3, "agent_started", {"prompt": "x"})],
            "the events are run_requested",
        ),
        (
            [
                REQUESTED,
                DESCRIBED,
                event(3, "error_occurred", {"error_code": "agent_crash", "error_message": "x"}),
            ],
            "error_occurred has the code agent_crash",
        ),
        ([REQUESTED, REFUSED], "the events are run_requested, error_occurred"),
        ([*REFUSAL, "not json"], "not a valid event: not json"),
        ([*REFUSAL, event(4, "from_the_future", {})], "not a valid event: {"),
        (None, "the agent wrote no Trajectory"),
    ],
)
def test_a_refusal_fails(fake: FakeDispatch, lines: list[dict | str] | None, problem: str) -> None:
    fake.lines = lines
    [outcome] = check.check("pd", [AGENTS_WITHOUT_ENTRY], MODEL)
    assert outcome.status == "fail"
    assert any(r.startswith(problem) for r in outcome.reasons), outcome.reasons


def test_a_failed_exit_fails(fake: FakeDispatch) -> None:
    fake.exit_code = 3
    [outcome] = check.check("pd", [AGENTS_WITHOUT_ENTRY], MODEL)
    assert (outcome.status, outcome.reasons) == ("fail", ["the agent exited with 3"])


def test_outcomes_keep_the_cases_order() -> None:
    def skip(context: Context) -> Commission:
        raise Skip("the agent has no subagents")

    def wrong(run: Run) -> list[str]:
        return ["wrong"]

    chosen = [case("one", check=wrong), case("two", commission=skip), case("three")]
    outcomes = check.check("pd", chosen, MODEL)
    assert [(o.case, o.status, o.reasons) for o in outcomes] == [
        ("one", "fail", ["wrong"]),
        ("two", "skip", ["the agent has no subagents"]),
        ("three", "pass", []),
    ]
    assert outcomes[1].run_directory is None


def test_only_skipped_cases_start_no_run(fake: FakeDispatch) -> None:
    def skip(context: Context) -> Commission:
        raise Skip("no")

    [outcome] = check.check("pd", [case(commission=skip)], MODEL)
    assert outcome.status == "skip"
    assert fake.commissions == []


def test_a_run_that_did_not_start_fails_with_why(fake: FakeDispatch) -> None:
    fake.error = Failed("OpenSandbox couldn't start a sandbox")
    [outcome] = check.check("pd", [case()], MODEL)
    assert outcome.status == "fail"
    assert outcome.reasons == ["the run didn't start: OpenSandbox couldn't start a sandbox"]
    assert outcome.run_directory is None


def test_a_check_that_raises_fails_with_why() -> None:
    def broken(run: Run) -> list[str]:
        raise KeyError("bug")

    [outcome] = check.check("pd", [case(check=broken)], MODEL)
    assert outcome.status == "fail"
    assert outcome.reasons == ["scorer failed: KeyError: 'bug'"]


def test_runs_get_the_stand_in_and_the_url_that_never_resolves(fake: FakeDispatch) -> None:
    check.check("pd", [case()], MODEL)
    [commission] = fake.commissions
    [options] = fake.options
    assert commission.model.base_url == check.BASE_URL
    assert commission.run_id == "conformance-pd-a-case"
    assert commission.supervisor is not None
    assert options.env == {check.KEY: check.STAND_IN}


def test_model_must_be_provider_slash_id() -> None:
    assert check.model("openai/gpt-5-mini").model_dump(exclude_none=True) == {
        "provider": "openai",
        "id": "gpt-5-mini",
        "base_url": check.BASE_URL,
        "credential": {"env": check.KEY},
    }
    with pytest.raises(Failed, match="isn't provider/model"):
        check.model("gpt-5-mini")


@pytest.mark.parametrize(("level", "exit_code"), [("MUST", 1), ("SHOULD", 0)])
def test_only_a_must_failure_exits_1(
    monkeypatch: pytest.MonkeyPatch, level: str, exit_code: int
) -> None:
    def wrong(run: Run) -> list[str]:
        return ["wrong"]

    monkeypatch.setattr(cli, "CASES", [case(level=level, check=wrong)])
    result = CliRunner().invoke(app, ["conformance", "check", "--agent", "pd", "--json"])
    assert result.exit_code == exit_code, result.output
    [outcome] = json.loads(result.output[result.output.index("[") :])
    assert (outcome["status"], outcome["reasons"]) == ("fail", ["wrong"])


def test_list_shows_each_rule_and_its_cases() -> None:
    result = CliRunner().invoke(app, ["conformance", "list", "--rule", "commission.5.1"])
    assert result.exit_code == 0, result.output
    assert "agents-without-entry" in result.output
    assert "trajectory.4.5" not in result.output


def test_unknown_rule_fails() -> None:
    result = CliRunner().invoke(app, ["conformance", "check", "--agent", "pd", "--rule", "x.1"])
    assert result.exit_code == 1
    assert "no rule x.1" in str(result.exception)
