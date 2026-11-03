"""An in-memory credential store in place of the system's, a scratch AVP home,
and --verbose off."""

from collections.abc import Iterator
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from avp_cli import console
from avp_cli.eval import scorers, scoring


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
