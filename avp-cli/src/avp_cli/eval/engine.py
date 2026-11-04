"""Running an eval: each run the EvalConfig yields goes through the same
`dispatch` as `avp run`, and is then read and scored."""

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TypeVar

from avp_cli import paths
from avp_cli.agents import command, store
from avp_cli.console import Failed
from avp_cli.engine import images
from avp_cli.eval import results
from avp_cli.eval.config import EvalCase, EvalConfig
from avp_cli.eval.scoring import Result, Run, Score, read, score
from avp_cli.runs.dispatch import Options, dispatch
from avp_cli.sandbox import sandboxes

T = TypeVar("T")


async def run_eval(
    config: EvalConfig,
    directory: Path,
    options: Options | None = None,
    concurrency: int = 1,
    progress: Callable[[Result], None] = lambda _: None,
    started: Callable[[EvalCase], None] = lambda _: None,
) -> list[Result]:
    """Every run's result, in the EvalConfig's order. Runs go in `directory`
    under `runs/<run_id>/`, at most `concurrency` at once. `options` apply to
    every run, and their volumes and entrypoint to each describe too; their
    `directory` is set for each run. `started` is called as each
    run starts, and `progress` as each is scored. Each agent is described once, all at the same time and
    before any run, and saved in `directory` under `agents/<name>.json`. Raises
    Failed before any run when an agent isn't installed or doesn't describe
    itself. When cancelled, as by Ctrl-C, it deletes the sandboxes still
    running, which ends their agents."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    options = options or Options()
    agents = {name: _load(name, options.entrypoint) for name in config.agents}

    async def described(name: str, agent: store.Agent, entrypoint: list[str]) -> None:
        record = results.AgentRecord(
            name=name,
            image=agent.image,
            image_id=images.image_id(agent.image),
            descriptor=await _in_thread(
                command.describe_in_sandbox, agent, entrypoint, options.volumes
            ),
        )
        results.save_agent(directory, record)

    limit = asyncio.Semaphore(concurrency)

    async def one(case: EvalCase) -> Result:
        async with limit:
            started(case)
            agent, entrypoint = agents[case.agent]
            run_directory = directory / paths.EVAL_RUNS / case.built.run_id
            began = time.monotonic()
            try:
                finished = await _in_thread(
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
                    model=_model(case),
                    seconds=time.monotonic() - began,
                )
                result = await score(config.scorer, config.scorer_config, run, finished.directory)
        progress(result)
        return result

    try:
        await asyncio.gather(*(described(n, a, e) for n, (a, e) in agents.items()))
        return list(await asyncio.gather(*(one(c) for c in config)))
    except (asyncio.CancelledError, Failed):
        sandboxes.kill_all()
        raise


async def _in_thread(function: Callable[..., T], *args: object) -> T:
    """`function(*args)` in a daemon thread. Unlike `asyncio.to_thread`, an
    interrupted eval doesn't wait for the thread: its sandbox is deleted, and
    avp exits without it."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[T] = loop.create_future()

    def settle(result: T | None, error: BaseException | None) -> None:
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)  # ty: ignore[invalid-argument-type]

    def target() -> None:
        try:
            result, error = function(*args), None
        except BaseException as caught:
            result, error = None, caught
        # The loop has closed when the eval was interrupted.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(settle, result, error)

    threading.Thread(target=target, daemon=True).start()
    return await future


def _model(case: EvalCase) -> str:
    return f"{case.built.model.provider}/{case.built.model.id}"


def _load(name: str, entrypoint: list[str] | None) -> tuple[store.Agent, list[str]]:
    agent = store.load(name)
    return agent, entrypoint or images.entrypoint(agent.image)


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
        model=_model(case),
    )
    return Result(run, Score(value=0, passed=False, reasons=[f"the run didn't start: {error}"]))
