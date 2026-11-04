"""`--env` and `--env-file`, and the check against the Commission."""

from pathlib import Path

import pytest

from avp.commission import Commission
from avp_cli.console import Failed
from avp_cli.runs import environment

COMMISSION = Commission.model_validate(
    {
        "avp_version": "0.1",
        "run_id": "r",
        "prompt": "hi",
        "model": {"provider": "anthropic", "id": "m", "credential": {"env": "MODEL_KEY"}},
        "mcp_servers": [
            {
                "id": "db",
                "name": "DB",
                "type": "stdio",
                "command": ["db-mcp"],
                "env": {"DB_TOKEN": {"env": "DB_TOKEN"}, "PLAIN": "x"},
            },
            {
                "id": "web",
                "name": "Web",
                "type": "http",
                "url": "https://example.com/mcp",
                "headers": {"Authorization": {"env": "WEB_TOKEN"}, "X-Proxy": {"proxy": "p"}},
            },
        ],
    }
)


def test_env_file_then_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(
        '# keys\n\nA=1\nB="quoted"\nexport C=x=y\nD=${HOME}/x # not expanded\n'
    )
    monkeypatch.setenv("FROM_SHELL", "shell")
    given = environment.variables(["A=2", "FROM_SHELL"], [tmp_path / ".env"])
    assert given == {"A": "2", "B": "quoted", "C": "x=y", "D": "${HOME}/x", "FROM_SHELL": "shell"}


def test_env_copied_from_an_unset_variable_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOT_SET", raising=False)
    with pytest.raises(Failed, match="NOT_SET, which isn't set"):
        environment.variables(["NOT_SET"], [])


def test_env_file_line_without_a_value_fails(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("A=1\nB\n")
    with pytest.raises(Failed, match="names B without a value"):
        environment.variables([], [tmp_path / ".env"])


def test_references_are_the_env_secrets_only() -> None:
    assert environment.references(COMMISSION) == {
        "MODEL_KEY": "model.credential",
        "DB_TOKEN": "MCP server 'db', DB_TOKEN",
        "WEB_TOKEN": "MCP server 'web', Authorization",
    }


def test_check_names_what_is_missing() -> None:
    with pytest.raises(Failed, match=r"DB_TOKEN \(MCP server 'db', DB_TOKEN\), WEB_TOKEN"):
        environment.check(COMMISSION, {"MODEL_KEY": "k"})
    environment.check(COMMISSION, {"MODEL_KEY": "k", "DB_TOKEN": "t", "WEB_TOKEN": "w"})
