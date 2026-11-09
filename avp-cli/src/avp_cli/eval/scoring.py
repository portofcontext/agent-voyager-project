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

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    computed_field,
)

from avp.reports import StopReason
from avp.trajectory import Trajectory, avp_metadata, documents, parse_trajectory
from avp_cli import paths
from avp_cli.eval.schemas import Item, JsonObject
from avp_cli.eval.template import TemplateError, render


class Totals(BaseModel):
    """Reported usage across an ATIF document; unknown totals stay identified."""

    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0
    tool_calls: dict[str, int] = {}
    unknown_metrics: list[str] = []

    @classmethod
    def of(cls, trajectory: Trajectory | None) -> "Totals":
        totals = cls()
        if trajectory is None:
            return totals
        unknown: set[str] = set()
        for doc in documents(trajectory):
            for step in doc.steps:
                if step.source == "agent" and not step.is_copied_context:
                    totals.turns += step.llm_call_count if step.llm_call_count is not None else 1
                    usage = step.metrics
                    if step.llm_call_count != 0:
                        for source, target in (
                            ("prompt_tokens", "input_tokens"),
                            ("completion_tokens", "output_tokens"),
                            ("cost_usd", "cost_usd"),
                        ):
                            if usage is None or getattr(usage, source) is None:
                                unknown.add(target)
                    if usage:
                        totals.input_tokens += usage.prompt_tokens or 0
                        totals.output_tokens += usage.completion_tokens or 0
                        totals.cost_usd += usage.cost_usd or 0
                for call in step.tool_calls or []:
                    totals.tool_calls[call.function_name] = (
                        totals.tool_calls.get(call.function_name, 0) + 1
                    )
        final = trajectory.final_metrics
        if final:
            known = (final.extra or {}).get("avp", {}).get("known_totals", {})
            for source, target in (
                ("total_prompt_tokens", "input_tokens"),
                ("total_completion_tokens", "output_tokens"),
                ("total_cost_usd", "cost_usd"),
            ):
                value = getattr(final, source)
                if value is not None:
                    setattr(totals, target, value)
                    unknown.discard(target)
                elif source in known:
                    setattr(totals, target, known[source])
                    unknown.add(target)
        totals.unknown_metrics = sorted(unknown)
        return totals


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
    trajectory: Trajectory | None
    """The native ATIF document, including documents from external producers."""
    invalid_trajectory: list[JsonValue]
    """Invalid document contents, parsed as JSON or retained as text."""
    output: JsonValue = None
    """Typed AVP output, or the final root agent message for external ATIF."""
    reason: StopReason | None = None
    """The AVP stop reason, when present."""
    item: Item
    """The dataset item the run's Commission was filled from."""
    model: str | None = None
    """The Commission's model, `provider/id`."""
    seconds: float | None = None
    """How long the run took, from creating its sandbox to the agent's exit,
    or None when it didn't start."""

    @computed_field
    @property
    def totals(self) -> Totals:
        return Totals.of(self.trajectory)


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
    def scorer(cls, base: Path) -> Scorer:
        """The callable: validates the filled fields in `config`, then scores.
        `base` is the eval file's directory, for a scorer that reads or runs
        files beside it."""

        def score(input: ScorerInput) -> Score | Awaitable[Score]:
            return cls.model_validate(input.config).score(input.run)

        return score


def read(
    directory: Path,
    *,
    id: str,
    agent: str,
    commission: str,
    item: Item,
    exit_code: int | None,
    model: str | None = None,
    seconds: float | None = None,
) -> Run:
    """The run in `directory`, from its Trajectory."""
    trajectory, invalid = read_trajectory(directory / paths.TRAJECTORY)
    metadata = avp_metadata(trajectory) if trajectory else {}
    replies = [s.message for s in trajectory.steps if s.source == "agent"] if trajectory else []
    return Run(
        id=id,
        agent=agent,
        commission=commission,
        exit_code=exit_code,
        trajectory=trajectory,
        invalid_trajectory=invalid,
        output=metadata.get("output", replies[-1] if replies else None),
        reason=metadata.get("stop_reason"),
        item=item,
        model=model,
        seconds=seconds,
    )


def read_trajectory(path: Path) -> tuple[Trajectory | None, list[JsonValue]]:
    """Validate one ATIF document. Missing and malformed documents are distinct."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None, []
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return None, [text]
    try:
        return parse_trajectory(raw), []
    except (ValidationError, TypeError, ValueError):
        return None, [raw]


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
        (directory / paths.SCORER_ERROR).write_text(text)
    return Result(run, None, failure)


@dataclass(frozen=True)
class Summary:
    runs: int
    accuracy: float | None
    """The mean `value` of the runs that have a score, or None when none do."""
    pass_rate: float | None
    """The share of scored runs that passed."""
    scorer_failures: int
    """Runs whose scorer failed, left out of accuracy and pass rate."""


def summarize(scores: list[Score | None]) -> Summary:
    """`scores` has one entry per run: None where its scorer failed."""
    scored = [s for s in scores if s is not None]
    return Summary(
        runs=len(scores),
        accuracy=sum(s.value for s in scored) / len(scored) if scored else None,
        pass_rate=sum(s.passed for s in scored) / len(scored) if scored else None,
        scorer_failures=len(scores) - len(scored),
    )
