"""Running cases against an installed agent, through the eval engine: each case
is an item whose Commission was written from the agent's Descriptor, and a
scorer checks its run. Runs are kept in `~/.avp/conformance/<time>-<agent>/`."""

import re
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from opensandbox.models.sandboxes import Volume

from avp.commission import Commission, EnvSecret, Model
from avp.descriptor import AgentDescriptor
from avp_cli import paths
from avp_cli.agents import command, store
from avp_cli.conformance import mock
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
"""The model's URL in a case with no responses, a name that never resolves, so
the sandbox allows no real provider. A case with responses has the mock model's."""
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


def check(
    agent: str,
    cases: list[Case],
    model: Model,
    concurrency: int = 1,
    volumes: list[Volume] | None = None,
    entrypoint: list[str] | None = None,
    mock_image: str = mock.IMAGE,
) -> list[Outcome]:
    """Every case's outcome, in the cases' order. `volumes` are mounted, and
    `entrypoint` replaces the image's, in every sandbox the agent runs in. The
    mock model starts from `mock_image` only when a case has responses."""
    directory = paths.conformance() / paths.stamped(agent, datetime.now(UTC))
    directory.mkdir(parents=True)
    installed = store.load(agent)
    command_line = entrypoint or images.entrypoint(installed.image)
    mounts = volumes or []
    with err.status(line("Getting the agent's Descriptor")):
        descriptor = command.describe_in_sandbox(installed, command_line, mounts)
    _check_supported(agent, descriptor, model)
    mocked = [case for case in cases if case.responses]
    provider_path = mock.path(model.provider) if mocked else ""
    written: dict[str, Commission] = {}
    outcomes: dict[str, Outcome] = {}
    with mock.serving(mocked, mock_image) if mocked else nullcontext("") as mock_url:
        for case in cases:
            context = Context(descriptor=descriptor, model=model)
            if case.responses:
                url = model.model_copy(update={"base_url": f"{mock_url}{provider_path}"})
                context = Context(descriptor=descriptor, model=url, prompt=case.prompt)
            try:
                written[case.name] = case.commission(context)
            except Skip as skip:
                outcomes[case.name] = _outcome(case, "skip", [str(skip)], None)
        if written:
            by_name = {case.name: case for case in cases}
            config = EvalConfig(
                check_commissions=False,
                name=NAME,
                agents=[agent],
                commissions={NAME: {"$item": "commission"}},
                dataset=[_item(by_name[name], c) for name, c in written.items()],
                scorer=_scorer(by_name),
            )
            options = Options(env={KEY: STAND_IN}, volumes=mounts, entrypoint=entrypoint)
            kept = directory / paths.EVAL_RUNS
            for result in run_live(config, directory, options, concurrency, kept):
                case = by_name[result.run.item.id]
                outcomes[case.name] = _from_result(case, result, directory)
    return [outcomes[case.name] for case in cases]


def _check_supported(agent: str, descriptor: AgentDescriptor, model: Model) -> None:
    """Stops a check the agent can't run: it would refuse every Commission for
    its model, so refusal cases would pass for the wrong reason. A Descriptor
    with no `supported_models` doesn't say, so the check runs."""
    patterns = descriptor.supported_models
    if patterns is None or any(
        _matches(p.provider, model.provider) and _matches(p.id, model.id) for p in patterns
    ):
        return
    listed = ", ".join(f"{p.provider}/{p.id}" for p in patterns) or "none"
    raise Failed(
        f"{agent} doesn't support {model.provider}/{model.id}; its Descriptor lists {listed}. "
        "--model names another"
    )


def _matches(pattern: str, value: str) -> bool:
    """A Model pattern's field: `*` matches any characters."""
    return re.fullmatch(".*".join(re.escape(p) for p in pattern.split("*")), value) is not None


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
