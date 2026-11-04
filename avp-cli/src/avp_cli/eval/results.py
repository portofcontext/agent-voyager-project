"""An eval run's directory, `~/.avp/evals/<time>-<name>/`: the eval file as
given, `results.json`, and each run's directory under `runs/`."""

import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from avp.descriptor import AgentDescriptor
from avp_cli import paths
from avp_cli.console import Failed
from avp_cli.eval.scoring import Result, Score, Summary, Totals, summarize


class RunResult(BaseModel):
    """One run's outcome, as saved."""

    run_id: str
    commission: str
    agent: str
    item: str
    """The item's `id`."""
    exit_code: int | None
    reason: str | None
    """`agent_stopped`'s `reason`, or None when there is none."""
    score: Score | None
    """None when the scorer failed."""
    scorer_error: str | None = None
    """Why the scorer failed. The full error is in the run's `scorer-error.txt`."""
    directory: str
    """The run's directory, relative to the eval's."""
    model: str | None = None
    """The Commission's model, `provider/id`."""
    seconds: float | None = None
    """How long the run took, or None when it didn't start."""
    totals: Totals = Totals()
    """Turns, tokens, cost, and tool calls, from the Trajectory."""

    @classmethod
    def of(cls, result: Result, eval_directory: Path) -> "RunResult":
        run = result.run
        return cls(
            run_id=run.id,
            commission=run.commission,
            agent=run.agent,
            item=run.item.id,
            exit_code=run.exit_code,
            reason=run.reason,
            score=result.score,
            scorer_error=result.error.message if result.error else None,
            directory=str(Path(paths.EVAL_RUNS) / run.id),
            model=run.model,
            seconds=run.seconds,
            totals=run.totals,
        )


class EvalResults(BaseModel):
    """`results.json`. Written as each run is scored, so an eval that stops
    early keeps the runs it finished; `finished` is set at the end."""

    id: str
    """The eval run's directory name, `<time>-<name>`."""
    name: str
    started: datetime
    finished: datetime | None = None
    runs: list[RunResult] = []

    def of(self, commission: str | None = None, agent: str | None = None) -> list[RunResult]:
        """The runs of `commission` on `agent`, or of all."""
        return [
            r
            for r in self.runs
            if (commission is None or r.commission == commission)
            and (agent is None or r.agent == agent)
        ]

    def summary(self, commission: str | None = None, agent: str | None = None) -> Summary:
        """The summary of the runs of `commission` on `agent`, or of all."""
        return summarize([r.score for r in self.of(commission, agent)])


class AgentRecord(BaseModel):
    """`agents/<name>.json`: the agent as it was when the eval ran, from one
    `describe` before the runs."""

    name: str
    image: str
    image_id: str
    """The engine's ID for the image, which changes when the agent is
    installed again."""
    descriptor: AgentDescriptor


def save_agent(directory: Path, record: AgentRecord) -> None:
    path = directory / paths.EVAL_AGENTS / f"{record.name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2, exclude_none=True) + "\n")


def agents(directory: Path) -> dict[str, AgentRecord]:
    """The eval's agents, by name. Empty for an eval that stopped before
    describing them."""
    folder = directory / paths.EVAL_AGENTS
    found = sorted(folder.glob("*.json")) if folder.is_dir() else []
    return {p.stem: AgentRecord.model_validate_json(p.read_text()) for p in found}


def create(name: str, eval_text: str) -> tuple[Path, EvalResults]:
    """A new eval run's directory, holding the eval file."""
    started = datetime.now(UTC)
    id = paths.stamped(name, started)
    directory = paths.evals() / id
    while True:
        try:
            directory.mkdir(parents=True)
            break
        except FileExistsError:
            id = f"{paths.stamped(name, started)}-{uuid4().hex}"
            directory = paths.evals() / id
    (directory / paths.EVAL).write_text(eval_text)
    results = EvalResults(id=id, name=name, started=started)
    save(directory, results)
    return directory, results


def save(directory: Path, results: EvalResults) -> None:
    (directory / paths.RESULTS).write_text(results.model_dump_json(indent=2) + "\n")


def ids() -> list[str]:
    """Every eval run's ID, the earliest first."""
    root = paths.evals()
    return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


def load(id: str | None = None) -> tuple[Path, EvalResults]:
    """An eval run by its ID, or the latest."""
    if id is None:
        found = ids()
        if not found:
            raise Failed("no evals have run yet")
        id = found[-1]
    directory = paths.evals() / id
    try:
        text = (directory / paths.RESULTS).read_text()
    except FileNotFoundError:
        raise Failed(f"no eval {id!r}; `avp eval list` shows them") from None
    return directory, EvalResults.model_validate_json(text)


def delete(id: str) -> None:
    """Delete an eval run's directory, with its runs' directories. Only an
    ID `ids` lists, so a path can't reach outside ~/.avp/evals/."""
    if id not in ids():
        raise Failed(f"no eval {id!r}; `avp eval list` shows them")
    shutil.rmtree(paths.evals() / id)
