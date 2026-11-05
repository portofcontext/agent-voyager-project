"""`avp hello-world`: a small eval on a few agents, with a mock model in place
of a real one, so it needs no credential and costs nothing."""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Any

import typer

from avp_cli import console
from avp_cli._cli_common import VerboseOption
from avp_cli.agents import cli as agent_cli
from avp_cli.agents import store
from avp_cli.conformance import mock
from avp_cli.conformance.cases import Response
from avp_cli.console import Failed, err, out
from avp_cli.engine import images
from avp_cli.eval import cli as eval_cli
from avp_cli.eval import share as sharing
from avp_cli.eval.commission import EvalError
from avp_cli.eval.config import EvalConfig
from avp_cli.eval.report import print_scoreboard
from avp_cli.eval.schemas import Eval
from avp_cli.runs.dispatch import Options

AGENTS = ("pydantic-ai", "pi", "deep-agents")
"""Built-in agents that run the same model."""
PROVIDER = "openai"
MODEL = "gpt-5.4-mini"
PROMPT = "What is the capital of {country}? Answer with the city's name only."
CAPITALS = {"France": "Paris", "Japan": "Tokyo", "Kenya": "Nairobi"}
KEY = "AVP_HELLO_WORLD_API_KEY"
STAND_IN = "avp-hello-world-stand-in"
"""The model's credential in the mocked runs, for runtimes that won't start
without a key."""
CONCURRENCY = 3


@dataclass(frozen=True)
class Reply:
    """What the mock model answers a prompt with."""

    prompt: str
    responses: tuple[Response, ...]


def eval_file(agents: list[str], model: dict[str, Any]) -> dict[str, Any]:
    return {
        "eval_version": "0.1",
        "name": "hello-world",
        "agents": agents,
        "commission": {
            "avp_version": "0.1",
            "model": {"provider": PROVIDER, "id": MODEL, **model},
            "prompt": PROMPT.format(country="{item.country}"),
        },
        "dataset": [
            {"id": country.lower(), "country": country, "answer": capital}
            for country, capital in CAPITALS.items()
        ],
        "scorer": {"name": "match", "expected": "{item.answer}"},
    }


def hello_world(
    no_share: Annotated[
        bool, typer.Option("--no-share", help="Don't upload the eval for a link.")
    ] = False,
    verbose: VerboseOption = False,
) -> None:
    """Run an example eval on three agents, print its scoreboard, and share it
    on agentvoyagerproject.com for a link. A mock model answers in place of a
    real one, so no credential is needed, nothing is billed, and the upload
    holds only the example's text and what the built-in agents say of
    themselves. Installs the agents that aren't installed."""
    console.set_verbose(verbose)
    agents = list(AGENTS)
    installed = {found.name for found in store.installed() if images.exists(found.image)}
    for name in agents:
        if name not in installed:
            agent_cli.install(name)
    replies = [
        Reply(PROMPT.format(country=country), ({"content": capital},))
        for country, capital in CAPITALS.items()
    ]
    with mock.serving(replies) as address:
        mocked = {"base_url": address + mock.path(PROVIDER), "credential": {"env": KEY}}
        try:
            config = EvalConfig.from_eval(
                Eval.model_validate(eval_file(agents, mocked)), Path.cwd()
            )
        except EvalError as error:
            raise Failed("\n".join(error.problems)) from None
        # The stand-in credential would draw a warning for every run.
        config = replace(config, check_commissions=False)
        real = eval_file(agents, {"credential": {"proxy": PROVIDER}})
        directory, saved = eval_cli.run_and_save(
            config, json.dumps(real, indent=2) + "\n", Options(env={KEY: STAND_IN}), CONCURRENCY
        )
    print_scoreboard(out, saved, directory)
    if no_share:
        return
    try:
        with err.status("Uploading"):
            shared = sharing.share(directory, saved, sharing.SITE)
    except Failed as failure:
        err.print(f"Not shared: {failure}", highlight=False, soft_wrap=True)
        return
    out.print(f"\n{shared.url}", highlight=False, soft_wrap=True)
