"""Built-in agents: published images or Dockerfiles that install released packages."""

import json
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from avp_cli.console import Failed

PACKAGE = Path(__file__).parent


@dataclass(frozen=True)
class Agent:
    agent_name: str
    version: str
    image: str | None = None
    """The published image, pinned by digest. None when this agent's version
    has no published image, so its Dockerfile installs the released package."""


@dataclass(frozen=True)
class Catalog:
    agents: dict[str, Agent]


def catalog() -> Catalog:
    data = json.loads((PACKAGE / "builtins.json").read_text())
    return Catalog(
        agents={name: Agent(**agent) for name, agent in data["agents"].items()},
    )


def get(name: str) -> Agent:
    agents = catalog().agents
    if name not in agents:
        raise Failed(
            f"{name!r} is not a built-in agent. Built-in names: {', '.join(agents)}. "
            "For a custom agent, provide its Dockerfile."
        )
    return agents[name]


@contextmanager
def context(name: str) -> Generator[Path]:
    """An empty build context containing the released agent's Dockerfile."""
    get(name)
    with tempfile.TemporaryDirectory(prefix="avp-agent-") as temporary:
        directory = Path(temporary)
        shutil.copyfile(PACKAGE / "dockerfiles" / f"{name}.Dockerfile", directory / "Dockerfile")
        yield directory
