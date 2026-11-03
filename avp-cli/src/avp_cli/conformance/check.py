"""Running cases against an installed agent: one sandbox for its Descriptor,
then a fresh sandbox per case. Each case's run keeps its Commission,
Trajectory, and stderr in `~/.avp/runs/`, as `avp run` does."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from avp.commission import EnvSecret, Model
from avp.trajectory import Event, parse_trajectory_event
from avp_cli import paths
from avp_cli.agents import command, store
from avp_cli.conformance.cases import Case, Context, Level, Run, Skip
from avp_cli.console import Failed, detail
from avp_cli.engine import images
from avp_cli.runs import directory
from avp_cli.sandbox import sandboxes

KEY = "AVP_CONFORMANCE_API_KEY"
STAND_IN = "avp-conformance-stand-in"
"""The model's credential in every case: a stand-in in the agent's environment,
for runtimes that won't start without a key. No case reaches a real model."""

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
    """`provider/id`, with the stand-in credential."""
    provider, sep, id = text.partition("/")
    if not sep or not provider or not id:
        raise Failed(f"--model {text!r} isn't provider/model, such as anthropic/claude-haiku-4-5")
    return Model(provider=provider, id=id, credential=EnvSecret(env=KEY))


def check(
    agent: str,
    cases: list[Case],
    model: Model,
    progress: Callable[[str], None] = lambda _: None,
) -> list[Outcome]:
    installed = store.load(agent)
    entrypoint = images.entrypoint(installed.image)
    progress("Getting the agent's Descriptor")
    with sandboxes.sandbox(installed.image) as box:
        descriptor = command.describe(box, entrypoint)
    context = Context(descriptor=descriptor, model=model)
    outcomes = []
    for case in cases:
        progress(f"Running {case.rule} {case.name}")
        outcomes.append(_run_case(installed, entrypoint, context, case))
    return outcomes


def _run_case(
    installed: store.Agent, entrypoint: list[str], context: Context, case: Case
) -> Outcome:
    def outcome(status: Status, reasons: list[str], run_directory: Path | None) -> Outcome:
        return Outcome(case.name, case.rule, case.level, status, reasons, run_directory)

    try:
        commission = case.commission(context)
    except Skip as skip:
        return outcome("skip", [str(skip)], None)
    text = commission.model_dump_json(exclude_none=True)
    run_directory = directory.create(commission.run_id, text)
    detail(f"{case.name}: run directory {run_directory}")
    # No host is allowed: a case that needs the model or an MCP server adds its own.
    with sandboxes.sandbox(installed.image, run_directory, []) as box:
        result = command.run(
            box,
            entrypoint,
            f"{sandboxes.IO}/{paths.COMMISSION}",
            f"{sandboxes.IO}/{paths.TRAJECTORY}",
            {KEY: STAND_IN},
        )
    if result.stderr:
        (run_directory / paths.STDERR).write_text(result.stderr)
    events, types, problems = read(run_directory / paths.TRAJECTORY)
    if result.exit_code != 0:
        problems.append(f"the agent exited with {result.exit_code}")
    problems += case.check(Run(events=events, types=types, exit_code=result.exit_code))
    return outcome("fail" if problems else "pass", problems, run_directory)


def read(trajectory: Path) -> tuple[list[Event | None], list[str], list[str]]:
    """One entry per line, in order: the event, or None when avp doesn't know
    its type or it isn't valid; and its `type`, or `?` when it has none. Then
    the problems with lines that aren't valid events."""
    events: list[Event | None] = []
    types: list[str] = []
    problems: list[str] = []
    try:
        lines = trajectory.read_text().splitlines()
    except FileNotFoundError:
        return [], [], ["the agent wrote no Trajectory"]
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raw, event = None, None
            problems.append(f"line {number} isn't JSON: {error}")
        else:
            try:
                event = parse_trajectory_event(raw)
            except ValidationError as error:
                event = None
                first = error.errors()[0]
                where = ".".join(map(str, first["loc"]))
                problems.append(f"line {number} isn't a valid event: {where}: {first['msg']}")
        events.append(event)
        types.append(str(raw.get("type", "?")) if isinstance(raw, dict) else "?")
    return events, types, problems
