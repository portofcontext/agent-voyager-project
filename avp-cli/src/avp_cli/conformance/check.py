"""Running cases against an installed agent, through the eval engine: each case
is an item whose Commission was written from the agent's Descriptor, and a
scorer checks its run. Runs are kept in `~/.avp/conformance/<time>-<agent>/`."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from avp.commission import Commission, EnvSecret, Model
from avp_cli import paths
from avp_cli.agents import command, store
from avp_cli.conformance.cases import Case, Context, Level, Skip
from avp_cli.console import Failed, err, line
from avp_cli.engine import images
from avp_cli.eval.config import EvalConfig
from avp_cli.eval.live import run_live
from avp_cli.eval.report import why
from avp_cli.eval.results import RunResult
from avp_cli.eval.schemas import Item
from avp_cli.eval.scoring import Result, Score, Scorer, ScorerInput
from avp_cli.runs.dispatch import Options

KEY = "AVP_CONFORMANCE_API_KEY"
STAND_IN = "avp-conformance-stand-in"
"""The model's credential in every case: a stand-in in the agent's environment,
for runtimes that won't start without a key. No case reaches a real model."""
BASE_URL = "http://conformance.invalid"
"""The model's URL in every case, a name that never resolves, so the sandbox
allows no real provider. The mock model's URL replaces it."""
NAME = "conformance"

Status = Literal["pass", "fail", "skip"]


@dataclass(frozen=True)
class Outcome:
    case: str
    rule: str
    level: Level
    status: Status
    reasons: list[str]
    run_directory: Path | None


def model(text: str) -> Model:
    """`provider/id`, with the stand-in credential and URL."""
    provider, sep, id = text.partition("/")
    if not sep or not provider or not id:
        raise Failed(f"--model {text!r} isn't provider/model, such as anthropic/claude-haiku-4-5")
    return Model(provider=provider, id=id, base_url=BASE_URL, credential=EnvSecret(env=KEY))


def check(agent: str, cases: list[Case], model: Model, concurrency: int = 1) -> list[Outcome]:
    """Every case's outcome, in the cases' order."""
    directory = paths.conformance() / paths.stamped(agent, datetime.now(UTC))
    directory.mkdir(parents=True)
    installed = store.load(agent)
    entrypoint = images.entrypoint(installed.image)
    with err.status(line("Getting the agent's Descriptor")):
        descriptor = command.describe_in_sandbox(installed, entrypoint)
    context = Context(descriptor=descriptor, model=model)
    written: dict[str, Commission] = {}
    outcomes: dict[str, Outcome] = {}
    for case in cases:
        try:
            written[case.name] = case.commission(context)
        except Skip as skip:
            outcomes[case.name] = _outcome(case, "skip", [str(skip)], None)
    if written:
        by_name = {case.name: case for case in cases}
        config = EvalConfig(
            name=NAME,
            agents=[agent],
            commissions={NAME: {"$item": "commission"}},
            dataset=[_item(by_name[name], c) for name, c in written.items()],
            scorer=_scorer(by_name),
        )
        options = Options(env={KEY: STAND_IN})
        kept = directory / paths.EVAL_RUNS
        for result in run_live(config, directory, options, concurrency, kept):
            case = by_name[result.run.item.id]
            outcomes[case.name] = _from_result(case, result, directory)
    return [outcomes[case.name] for case in cases]


def _item(case: Case, commission: Commission) -> Item:
    return Item(
        id=case.name,
        rule=case.rule,
        level=case.level,
        commission=commission.model_dump(mode="json", exclude_none=True),
    )


def _scorer(cases: dict[str, Case]) -> Scorer:
    """Passes a run with nothing wrong in its Trajectory or exit code, and
    nothing wrong by its case's check."""

    def score(input: ScorerInput) -> Score:
        run = input.run
        problems = [f"not a valid event: {i}" for i in run.invalid_trajectory]
        if not run.trajectory and not run.invalid_trajectory:
            problems.append("the agent wrote no Trajectory")
        if run.exit_code != 0:
            problems.append(f"the agent exited with {run.exit_code}")
        problems += cases[run.item.id].check(run)
        return Score(value=0 if problems else 1, passed=not problems, reasons=problems)

    return score


def _from_result(case: Case, result: Result, directory: Path) -> Outcome:
    """A run that didn't start or that its scorer couldn't score has failed,
    and says why."""
    run = RunResult.of(result, directory)
    if run.score is not None and run.score.passed:
        return _outcome(case, "pass", [], directory / run.directory)
    started = run.seconds is not None
    return _outcome(
        case, "fail", why(run).plain.splitlines(), directory / run.directory if started else None
    )


def _outcome(case: Case, status: Status, reasons: list[str], run_directory: Path | None) -> Outcome:
    return Outcome(case.name, case.rule, case.level, status, reasons, run_directory)
