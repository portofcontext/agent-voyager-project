"""`avp vault set`, `list`, and `delete`, against an in-memory credential store."""

import sys

import keyring
import pytest
from conftest import Memory
from keyring.errors import KeyringError
from typer.testing import CliRunner

from avp_cli import paths
from avp_cli.cli import app, main
from avp_cli.vault import store


def described(secrets: list[store.Secret]) -> list[tuple[str, str | None]]:
    return [(secret.name, secret.description) for secret in secrets]


def test_set_list_delete(memory: Memory) -> None:
    runner = CliRunner()
    set_openai = ["vault", "set", "openai", "sk-1", "-d", "Personal key"]
    assert runner.invoke(app, set_openai).exit_code == 0
    assert runner.invoke(app, ["vault", "set", "anthropic"], input="sk-2\n").exit_code == 0
    assert memory.values == {("avp", "openai"): "sk-1", ("avp", "anthropic"): "sk-2"}

    listed = runner.invoke(app, ["vault", "list"]).stdout.splitlines()
    assert listed[0].split() == ["Name", "Description", "Updated", "Expires"]
    assert listed[2].split()[:3] == ["openai", "Personal", "key"]
    assert "sk-" not in "".join(listed)

    first = store.secrets()[1].updated
    assert runner.invoke(app, ["vault", "set", "openai", "sk-3"]).exit_code == 0
    assert memory.values[("avp", "openai")] == "sk-3"
    assert described(store.secrets()) == [("anthropic", None), ("openai", "Personal key")]
    assert store.secrets()[1].updated > first

    assert runner.invoke(app, ["vault", "set", "openai", "sk-3", "-d", ""]).exit_code == 0
    assert described(store.secrets()) == [("anthropic", None), ("openai", None)]

    assert runner.invoke(app, ["vault", "delete", "openai"]).exit_code == 0
    assert memory.values == {("avp", "anthropic"): "sk-2"}
    assert described(store.secrets()) == [("anthropic", None)]


def test_delete_unknown_fails(memory: Memory) -> None:
    with pytest.raises(store.Failed, match="no secret named 'nope'"):
        store.delete("nope")


def test_list_check_flags_secrets_removed_outside_avp(memory: Memory) -> None:
    store.set_("openai", "sk-1")
    store.set_("anthropic", "sk-2")
    runner = CliRunner()
    assert runner.invoke(app, ["vault", "list", "--check"]).exit_code == 0

    del memory.values[("avp", "openai")]
    assert "✗" not in runner.invoke(app, ["vault", "list"]).output
    checked = runner.invoke(app, ["vault", "list", "--check"])
    rows = [line.split() for line in checked.stdout.splitlines()[1:]]
    assert [(row[0], row[-1]) for row in rows] == [("anthropic", "✓"), ("openai", "✗")]
    assert isinstance(checked.exception, store.Failed)
    assert "not in the store: openai" in str(checked.exception)


def test_delete_after_removal_outside_avp(memory: Memory) -> None:
    store.set_("openai", "sk-1")
    memory.values.clear()
    store.delete("openai")
    assert store.secrets() == []


def test_name_must_match_a_proxy_reference() -> None:
    with pytest.raises(store.Failed, match="can't be a secret name"):
        store.check_name("OpenAI")


def test_verbose_names_the_store_and_never_a_value(memory: Memory) -> None:
    runner = CliRunner()
    quiet = runner.invoke(app, ["vault", "set", "openai", "sk-1"])
    assert "Credential store" not in quiet.stderr

    loud = runner.invoke(app, ["vault", "set", "openai", "sk-1", "--verbose"])
    assert loud.exit_code == 0, loud.output
    assert "Credential store: conftest Memory" in loud.stderr
    assert f"Names and descriptions: {paths.vault()}" in loud.stderr
    assert "sk-1" not in loud.output


def test_verbose_failure_shows_its_cause(
    memory: Memory, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def locked(*_: object) -> None:
        raise KeyringError("the keychain is locked")

    monkeypatch.setattr(keyring, "set_password", locked)
    monkeypatch.setattr(sys, "argv", ["avp", "vault", "set", "openai", "sk-1", "--verbose"])
    with pytest.raises(SystemExit):
        main()
    assert "Caused by KeyringError: the keychain is locked" in capsys.readouterr().err
