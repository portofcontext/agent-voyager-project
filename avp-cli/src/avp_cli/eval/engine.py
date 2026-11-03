"""Running an eval: each run the EvalConfig yields goes through the same
`dispatch` as `avp run`, and is then read and scored."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from avp_cli.agents import store
from avp_cli.console import Failed
from avp_cli.engine import images
from avp_cli.eval.config import EvalCase, EvalConfig
from avp_cli.eval.scoring import Result, Run, Score, read, score
from avp_cli.runs.dispatch import Options, dispatch

RUNS = "runs"
"""In an eval's directory: one directory per run, named by its `run_id`."""


async def run_eval(
    config: EvalConfig,
    directory: Path,
    options: Options | None = None,
    concurrency: int = 1,
    progress: Callable[[Result], None] = lambda _: None,
) -> list[Result]:
    """Every run's result, in the EvalConfig's order. Runs go in `directory`
    under `runs/<run_id>/`, at most `concurrency` at once. `options` apply to
    every run; their `directory` is set for each. `progress` is called as
    each run is scored. Raises Failed before any run when an agent isn't
    installed."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    options = options or Options()
    agents = {name: _load(name) for name in config.agents}
    limit = asyncio.Semaphore(concurrency)

    async def one(case: EvalCase) -> Result:
        async with limit:
            agent, entrypoint = agents[case.agent]
            run_directory = directory / RUNS / case.built.run_id
            try:
                finished = await asyncio.to_thread(
                    dispatch,
                    agent,
                    entrypoint,
                    case.built,
                    replace(options, directory=run_directory),
                )
            except Failed as error:
                result = _not_started(case, error)
            else:
                run = read(
                    finished.directory,
                    id=case.built.run_id,
                    agent=case.agent,
                    commission=case.commission,
                    item=case.item,
                    exit_code=finished.exit_code,
                )
                result = await score(config.scorer, config.scorer_config, run, finished.directory)
        progress(result)
        return result

    return list(await asyncio.gather(*(one(c) for c in config)))


def _load(name: str) -> tuple[store.Agent, list[str]]:
    agent = store.load(name)
    return agent, images.entrypoint(agent.image)


def _not_started(case: EvalCase, error: Failed) -> Result:
    """A run whose agent never started fails with a score of 0."""
    run = Run(
        id=case.built.run_id,
        agent=case.agent,
        commission=case.commission,
        exit_code=None,
        trajectory=[],
        invalid_trajectory=[],
        item=case.item,
    )
    return Result(run, Score(value=0, passed=False, reasons=[f"the run didn't start: {error}"]))
