"""Commission commands through parsing, storage, validation, and run dispatch."""

import json
from pathlib import Path

import pytest
from conftest import no_sandbox
from pydantic import JsonValue
from typer.testing import CliRunner

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp_cli import paths
from avp_cli.agents import command
from avp_cli.agents import store as agents
from avp_cli.cli import app
from avp_cli.commissions import store
from avp_cli.commissions.check import check
from avp_cli.console import Failed
from avp_cli.runs import cli as run_cli
from avp_cli.runs.dispatch import Finished, Options

COMMISSION: dict[str, JsonValue] = {
    "avp_version": "0.1",
    "model": {"provider": "anthropic", "id": "claude-test"},
    "prompt": "Say hello.",
}
DESCRIPTOR = AgentDescriptor.model_validate(
    {
        "avp_version": "0.1",
        "agent_name": "sh-agent",
        "agent_version": "1.0.0",
        "tools": [
            {"name": "shell", "inputSchema": {"type": "object"}},
            {"name": "search", "inputSchema": {"type": "object"}, "mcp_server_id": "web"},
        ],
        "mcp_servers": [{"id": "web"}],
        "skills": [{"name": "guide", "description": "A guide"}],
        "subagents": [{"name": "helper"}],
        "supported_models": [{"provider": "anthropic", "id": "claude-*"}],
    }
)


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path / "home"))


def write(tmp_path: Path, **changes: JsonValue) -> Path:
    path = tmp_path / "task.json"
    path.write_text(json.dumps({**COMMISSION, **changes}))
    return path


def invoke(*args: str):
    return CliRunner().invoke(app, list(args))


def test_new_uses_descriptor_name_pins_version_and_lists_only_builtin_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_sandbox(monkeypatch)
    monkeypatch.setattr(command, "describe_in_sandbox", lambda *args: DESCRIPTOR)
    result = invoke("commission", "new", "--agent", "alias", "--model", "anthropic/claude-test")
    assert result.exit_code == 0, result.exception
    value = json.loads(result.stdout)
    assert "run_id" not in value and "supervisor" not in value
    assert value["agents"] == {
        "sh-agent": {
            "version": "1.0.0",
            "enabled_tools": ["shell"],
            "enabled_mcp_servers": ["web"],
            "enabled_skills": ["guide"],
            "enabled_subagents": ["helper"],
        }
    }
    assert store.names() == []
    path = tmp_path / "new.json"
    path.write_text(result.stdout)
    assert invoke("commission", "check", str(path), "--agent", "alias").exit_code == 0


def test_all_independent_errors_and_warnings_are_reported(tmp_path: Path) -> None:
    server: JsonValue = {
        "id": "web",
        "type": "http",
        "url": "https://example.com/mcp",
        "headers": {"X-Key": "a", "x-key": {"env": "KEY"}},
    }
    skill: JsonValue = {"name": "guide", "files": {"SKILL.md": "---\nname: wrong\n---\n"}}
    path = write(tmp_path, prompt=42, mcp_servers=[server, server], skills=[skill, skill])
    result = invoke("commission", "check", str(path))
    assert result.exit_code == 1
    for expected in [
        "prompt",
        "duplicate 'web'",
        "duplicate 'guide'",
        "duplicate 'x-key'",
        "skills.0.name",
        "skills.1.name",
        "mcp_servers.0.headers.x-key",
        "KEY",
    ]:
        assert expected in result.output, result.output


def test_descriptor_errors_collect_every_enabled_list_and_warnings() -> None:
    value: dict[str, JsonValue] = {
        **COMMISSION,
        "agents": {
            "sh-agent": {
                "version": "old",
                "enabled_tools": ["search", "missing"],
                "enabled_subagents": ["none"],
                "enabled_skills": ["none"],
                "enabled_mcp_servers": ["none"],
            }
        },
        "mcp_servers": [{"id": "web", "type": "stdio", "command": ["web"]}],
        "skills": [{"name": "guide", "files": {"SKILL.md": "---\nname: guide\n---\n"}}],
        "model": {"provider": "openai", "id": "other"},
    }
    problems = check(value, DESCRIPTOR)
    errors = [p for p in problems if p.level == "error"]
    warnings = [p for p in problems if p.level == "warning"]
    assert len(errors) == 6
    assert len(warnings) == 3
    assert "search" in str(errors[2])
    assert {p.where for p in warnings} == {"mcp_servers.0.id", "skills.0.name", "model"}
    assert "no entry for 'sh-agent'" in str(
        check({**COMMISSION, "agents": {"alias": {}}}, DESCRIPTOR)
    )


def test_warnings_exit_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    no_sandbox(monkeypatch)
    monkeypatch.setattr(command, "describe_in_sandbox", lambda *args: DESCRIPTOR)
    path = write(tmp_path, model={"provider": "other", "id": "x", "credential": {"env": "KEY"}})
    result = invoke("commission", "check", str(path), "--agent", "alias")
    assert result.exit_code == 0, result.exception
    assert "env secret 'KEY'" in result.output
    assert "outside supported_models" in result.output


def test_save_list_replace_resolve_and_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write(tmp_path, run_id="old", supervisor={"name": "old"}, thread_id="conversation")
    assert invoke("commission", "save", "baseline", str(path)).exit_code == 0
    assert invoke("commission", "list").stdout.strip() == "baseline"
    saved = store.read(store.resolve("baseline"))
    assert "run_id" not in saved and "supervisor" not in saved
    assert saved["thread_id"] == "conversation"
    assert invoke("commission", "check", "baseline").exit_code == 0
    assert invoke("commission", "save", "baseline", str(path)).exit_code == 1
    assert invoke("commission", "save", "baseline", str(path), "--force").exit_code == 0
    monkeypatch.chdir(tmp_path)
    Path("baseline").write_text("local file")
    assert store.resolve("baseline") == paths.commissions() / "baseline.json"
    assert store.resolve("./baseline").read_text() == "local file"
    assert invoke("commission", "delete", "baseline", "--yes").exit_code == 0
    assert store.names() == []
    with pytest.raises(Failed, match="no saved Commission"):
        store.resolve("baseline")


@pytest.mark.parametrize("name", ["../outside", "task.json", "Bad Name", ".hidden", "a/b"])
def test_invalid_names_cannot_escape_library(name: str) -> None:
    with pytest.raises(Failed):
        store.save(name, COMMISSION)


def test_repeated_json_keys_are_not_silently_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "repeated.json"
    path.write_text('{"agents": {"pd": {}, "pd": {}}, "prompt": "a", "prompt": "b"}')
    result = invoke("commission", "check", str(path))
    assert result.exit_code == 1
    assert "repeats JSON keys: 'pd', 'prompt'" in str(result.exception)


def test_run_saved_and_file_replace_identity_and_keep_caller_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_sandbox(monkeypatch)
    path = write(
        tmp_path,
        run_id="old",
        supervisor={"name": "old"},
        thread_id="thread",
        tags=["tag"],
        meta={"ticket": 112},
    )
    store.save("baseline", store.read(path))
    sent: list[Commission] = []

    def dispatch(
        agent: agents.Agent,
        entrypoint: list[str],
        commission: Commission,
        options: Options,
        **kwargs: object,
    ) -> Finished:
        sent.append(commission)
        assert "text" not in kwargs  # The dispatcher serializes the finalized Commission.
        return Finished(tmp_path / commission.run_id, 0, "")

    monkeypatch.setattr(run_cli, "dispatch", dispatch)
    for source in ["baseline", "baseline", str(path), str(path)]:
        result = invoke("run", "--agent", "alias", "--commission", source)
        assert result.exit_code == 0, result.exception
    assert len({c.run_id for c in sent}) == 4
    for c in sent:
        assert c.run_id != "old"
        assert c.supervisor and c.supervisor.name == "avp-cli"
        assert (c.thread_id, c.tags, c.meta) == ("thread", ["tag"], {"ticket": 112})
    assert json.loads(path.read_text())["run_id"] == "old"


def test_run_stops_before_describe_or_dispatch_on_static_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    described = no_sandbox(monkeypatch)
    path = write(tmp_path, skills=[{"name": "guide", "files": {"SKILL.md": "no name"}}])
    monkeypatch.setattr(
        run_cli, "dispatch", lambda *a, **kw: pytest.fail("dispatched invalid file")
    )
    result = invoke("run", "--agent", "alias", "--commission", str(path))
    assert result.exit_code == 1
    assert isinstance(result.exception, Failed)
    assert "SKILL.md" in str(result.exception)
    assert described == []


def test_run_stops_before_dispatch_on_descriptor_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    described = no_sandbox(monkeypatch)
    path = write(tmp_path, agents={"alias": {}})
    monkeypatch.setattr(
        run_cli, "dispatch", lambda *a, **kw: pytest.fail("dispatched invalid file")
    )
    result = invoke("run", "--agent", "alias", "--commission", str(path))
    assert result.exit_code == 1
    assert "no entry for 'sh-agent'" in str(result.exception)
    assert described == ["alias"]
