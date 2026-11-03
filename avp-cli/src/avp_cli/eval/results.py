"""An eval run's directory, `~/.avp/evals/<time>-<name>/`: the eval file as
given, `results.json`, and each run's directory under `runs/`."""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from avp_cli import paths
from avp_cli.console import Failed
from avp_cli.eval.scoring import Result, Score, Summary, summarize


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

    def summary(self, commission: str | None = None, agent: str | None = None) -> Summary:
        """The summary of the runs of `commission` on `agent`, or of all."""
        return summarize(
            [
                r.score
                for r in self.runs
                if (commission is None or r.commission == commission)
                and (agent is None or r.agent == agent)
            ]
        )


def create(name: str, eval_text: str) -> tuple[Path, EvalResults]:
    """A new eval run's directory, holding the eval file."""
    started = datetime.now(UTC)
    id = paths.stamped(name, started)
    directory = paths.evals() / id
    directory.mkdir(parents=True)
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
