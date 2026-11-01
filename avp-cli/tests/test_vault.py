"""`avp vault set`, `list`, and `delete`, against an in-memory credential store."""

import pytest
from conftest import Memory
from typer.testing import CliRunner

from avp_cli.cli import app
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
