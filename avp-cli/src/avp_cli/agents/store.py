"""Installed agents, one JSON file each under `~/.avp/agents/`."""

import re

from pydantic import BaseModel

from avp_cli import paths
from avp_cli.console import Failed

NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")
"""Lowercase, since the name is part of the image's tag."""


class Agent(BaseModel):
    name: str
    image: str
    """The engine's name for the image. The agent's Descriptor is never saved:
    `describe` asks the agent each time."""


def check_name(name: str) -> None:
    if not NAME.fullmatch(name):
        raise Failed(
            f"{name!r} can't be an agent name: use lowercase letters, digits, '.', '_', and '-'"
        )


def save(agent: Agent) -> None:
    paths.agents().mkdir(parents=True, exist_ok=True)
    (paths.agents() / f"{agent.name}.json").write_text(agent.model_dump_json(indent=2))


def load(name: str) -> Agent:
    try:
        return Agent.model_validate_json((paths.agents() / f"{name}.json").read_text())
    except FileNotFoundError:
        raise Failed(f"no agent named {name!r}. `avp agent list` shows yours") from None


def installed() -> list[Agent]:
    return [
        Agent.model_validate_json(path.read_text())
        for path in sorted(paths.agents().glob("*.json"))
    ]


def delete(name: str) -> None:
    (paths.agents() / f"{name}.json").unlink(missing_ok=True)
