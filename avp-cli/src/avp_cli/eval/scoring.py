"""Scoring a finished run. Inside avp, a scorer is a callable, plain or async,
that takes a `ScorerInput` and returns a `Score`. The built-in scorers are
such callables, configured by the eval file's `scorer`, and conformance cases
can be too. See docs/eval.md, Scorers."""

import inspect
import json
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_serializer

from avp.trajectory import AgentStoppedEvent, Event, StopReason, parse_trajectory_event
from avp_cli.eval.schemas import Item, JsonObject
from avp_cli.eval.template import TemplateError, render
from avp_cli.runs.directory import TRAJECTORY

SCORER_ERROR = "scorer-error.txt"
"""In a run's directory: why its scorer failed, with the traceback or stderr."""


class InvalidEvent(BaseModel):
    """A Trajectory line that isn't a valid event."""

    line: int
    """Counted from 1."""
    error: str
    """Why the line isn't a valid event."""
    event: JsonValue
    """The line parsed as JSON, or its text when it isn't JSON."""


class Run(BaseModel):
    """A finished run, as a scorer sees it: the guide's `run`."""

    id: str
    """The run's `run_id`."""
    agent: str
    """The installed agent that ran."""
    commission: str
    """The Commission's name in the eval."""
    exit_code: int | None
    """The agent command's exit code, or None when the command didn't exit,
    such as when its sandbox stopped first."""
    trajectory: list[Event]
    """The valid events, in order. Types avp doesn't know are skipped."""
    invalid_trajectory: list[InvalidEvent]
    """The lines that aren't valid events, left out of `trajectory`."""
    output: JsonValue = None
    """`agent_stopped`'s `output`, or None when it has none or there is no
    `agent_stopped`."""
    reason: StopReason | None = None
    """`agent_stopped`'s `reason`, or None when there is no `agent_stopped`."""
    item: Item
    """The dataset item the run's Commission was filled from."""

    @field_serializer("trajectory")
    def _events(self, events: list[Event]) -> list[JsonValue]:
        return [e.model_dump(mode="json", exclude_none=True) for e in events]


class ScorerInput(BaseModel):
    """What every scorer takes, and what a `command` scorer reads as JSON."""

    run: Run
    """The finished run, which avp passes."""
    config: JsonObject = {}
    """The scorer's own fields, with placeholders filled."""


class Score(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Annotated[float, Field(ge=0, le=1)]
    """From 0 to 1. Partial credit is allowed."""
    passed: bool
    """Whether the run passed."""
    reasons: list[str] = []
    """Why the run lost points. Empty when it passed."""


Scorer = Callable[[ScorerInput], Score | Awaitable[Score]]


class ScorerError(Exception):
    """A scorer that couldn't score. `detail` is the traceback, or a
    command's stderr."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


async def call(scorer: Scorer, input: ScorerInput) -> Score:
    """The scorer's score, awaited when the scorer is async. Anything that
    goes wrong, including a result that isn't a Score, is a ScorerError."""
    try:
        result = scorer(input)
        if inspect.isawaitable(result):
            result = await result
    except ScorerError:
        raise
    except Exception as error:
        raise ScorerError(_describe(error), traceback.format_exc()) from error
    if not isinstance(result, Score):
        raise ScorerError(f"the scorer returned {type(result).__name__}, not a Score")
    return result


def _describe(error: Exception) -> str:
    return f"{type(error).__name__}: {error}" if str(error) else type(error).__name__


class ScorerConfig(BaseModel):
    """A built-in scorer's fields in the eval file, other than `name`.
    Placeholders in them are filled for each run, and the filled fields are
    validated again before `score`."""

    model_config = ConfigDict(extra="forbid")

    name: ClassVar[str]

    def score(self, run: Run) -> Score | Awaitable[Score]:
        raise NotImplementedError

    @classmethod
    def scorer(cls) -> Scorer:
        """The callable: validates the filled fields in `config`, then scores."""

        def score(input: ScorerInput) -> Score | Awaitable[Score]:
            return cls.model_validate(input.config).score(input.run)

        return score


SCORERS: dict[str, type[ScorerConfig]] = {}
"""The built-in scorers by `name`."""


def read(
    directory: Path, *, id: str, agent: str, commission: str, item: Item, exit_code: int | None
) -> Run:
    """The run in `directory`, from its Trajectory."""
    events, invalid = read_trajectory(directory / TRAJECTORY)
    stopped = [e for e in events if isinstance(e, AgentStoppedEvent)]
    return Run(
        id=id,
        agent=agent,
        commission=commission,
        exit_code=exit_code,
        trajectory=events,
        invalid_trajectory=invalid,
        output=stopped[-1].data.output if stopped else None,
        reason=stopped[-1].data.reason if stopped else None,
        item=item,
    )


def read_trajectory(path: Path) -> tuple[list[Event], list[InvalidEvent]]:
    """The valid events, and the lines that aren't valid events. A missing
    file is an empty Trajectory."""
    events: list[Event] = []
    invalid: list[InvalidEvent] = []
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return events, invalid
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            invalid.append(InvalidEvent(line=number, error=f"isn't JSON: {error}", event=line))
            continue
        if not isinstance(raw, dict):
            invalid.append(InvalidEvent(line=number, error="isn't a JSON object", event=raw))
            continue
        try:
            event = parse_trajectory_event(raw)
        except ValidationError as error:
            first = error.errors()[0]
            where = ".".join(map(str, first["loc"]))
            invalid.append(
                InvalidEvent(
                    line=number,
                    error=f"isn't a valid event: {where}: {first['msg']}",
                    event=raw,
                )
            )
            continue
        if event is not None:
            events.append(event)
    return events, invalid


@dataclass(frozen=True)
class Result:
    """A run and its score, or why its scorer failed."""

    run: Run
    score: Score | None
    error: ScorerError | None = None


async def score(scorer: Scorer, config: JsonObject, run: Run, directory: Path | None) -> Result:
    """Fills `config` from the run and its item, and scores the run. A
    failure is saved in `directory` as `scorer-error.txt`."""
    try:
        scope: dict[str, JsonValue] = {"item": run.item.model_dump(mode="json")}
        scope["run"] = run.model_dump(mode="json")
        filled = render(config, scope, "scorer")
        if not isinstance(filled, dict):
            raise ScorerError("scorer: the config isn't a JSON object once filled")
        return Result(run, await call(scorer, ScorerInput(run=run, config=filled)))
    except (TemplateError, ScorerError) as error:
        failure = error if isinstance(error, ScorerError) else ScorerError(str(error))
    if directory is not None:
        text = failure.message + (f"\n\n{failure.detail}" if failure.detail else "") + "\n"
        (directory / SCORER_ERROR).write_text(text)
    return Result(run, None, failure)


@dataclass(frozen=True)
class Summary:
    runs: int
    accuracy: float | None
    """The mean `value` of the runs that have a score, or None when none do."""
    pass_rate: float | None
    """The share of scored runs that passed."""
    scorer_failures: list[Result]
    """Runs whose scorer failed, left out of accuracy and pass rate."""


def summarize(results: list[Result]) -> Summary:
    scores = [r.score for r in results if r.score is not None]
    return Summary(
        runs=len(results),
        accuracy=sum(s.value for s in scores) / len(scores) if scores else None,
        pass_rate=sum(s.passed for s in scores) / len(scores) if scores else None,
        scorer_failures=[r for r in results if r.score is None],
    )
