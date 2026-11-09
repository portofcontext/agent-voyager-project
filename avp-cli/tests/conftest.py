"""An in-memory credential store in place of the system's, a scratch AVP home,
and --verbose off."""

import secrets
from collections.abc import Generator, Iterator
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
from opensandbox.models.sandboxes import Volume

from avp.descriptor import AgentDescriptor
from avp_cli import console
from avp_cli.agents import command, store
from avp_cli.engine import images
from avp_cli.eval import scorers, scoring
from avp_cli.sandbox import service

DESCRIPTOR = AgentDescriptor(avp_version="0.1", agent_name="sh-agent", agent_version="1.0.0")


class Described(list[str]):
    """The names described, with what the last describe was given."""

    entrypoint: list[str] | None = None
    volumes: list[Volume] | None = None


def no_sandbox(monkeypatch: pytest.MonkeyPatch) -> Described:
    """Installed agents, a describe that answers, and the names described."""
    described = Described()

    def describe(
        agent: store.Agent, entrypoint: list[str], volumes: list[Volume] | None = None
    ) -> AgentDescriptor:
        described.append(agent.name)
        described.entrypoint = entrypoint
        described.volumes = volumes
        return DESCRIPTOR

    monkeypatch.setattr(store, "load", lambda name: store.Agent(name=name, image=f"avp/{name}"))
    monkeypatch.setattr(images, "entrypoint", lambda image: ["/agent"])
    monkeypatch.setattr(images, "image_id", lambda image: f"sha256:{image}")
    monkeypatch.setattr(command, "describe_in_sandbox", describe)
    return described


def atif(*, steps=None, complete=True, output="Paris", run_id="r", error=None):
    """A native ATIF document, including AVP's optional run outcome."""
    meta = {"complete": complete}
    if complete:
        meta.update(stop_reason="error" if error else "converged")
        if output is not None and not error:
            meta["output"] = output
    if error:
        steps = [
            {
                "step_id": 1,
                "source": "system",
                "message": error[1],
                "extra": {"avp": {"error_code": error[0]}},
            }
        ]
    if steps is None:
        steps = [{"step_id": 1, "source": "user", "message": "Name the city"}]
        if complete and output is not None:
            steps.append({"step_id": 2, "source": "agent", "message": output})
    return {
        "schema_version": "ATIF-v1.8",
        "session_id": run_id,
        "agent": {"name": "sh-agent", "version": "1.0.0"},
        "steps": steps,
        "extra": {"avp": meta},
    }


class Memory(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.values.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture
def memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Memory]:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    backend = Memory()
    previous = keyring.get_keyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def quiet() -> Iterator[None]:
    """A command's --verbose stays set in the process; each test starts and ends
    without it."""
    console.set_verbose(False)
    yield
    console.set_verbose(False)


@pytest.fixture(autouse=True)
def fixed_scorer(monkeypatch: pytest.MonkeyPatch) -> None:
    """`fixed`, a built-in scorer for eval tests: every run gets `value`."""

    class Fixed(scoring.ScorerConfig):
        name = "fixed"
        value: float = 1

        def score(self, run: scoring.Run) -> scoring.Score:
            return scoring.Score(value=self.value, passed=self.value == 1)

    monkeypatch.setitem(scorers.SCORERS, "fixed", Fixed)


TEST_PORT = 18799


@pytest.fixture(scope="module")
def avp_home(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path]:
    home = tmp_path_factory.mktemp("avp")
    with pytest.MonkeyPatch.context() as patch:
        # Its own port, so it never meets the service on avp's.
        patch.setattr(service, "PORT", TEST_PORT)
        if service.running():
            pytest.skip(f"an OpenSandbox service is already running on {TEST_PORT}")
        patch.setenv("AVP_HOME", str(home))
        patch.setenv(service.KEY_ENV, secrets.token_hex(32))
        yield home
        service.stop()
