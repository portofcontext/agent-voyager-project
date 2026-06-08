"""Building commissions into the library: `commission.build_commission` (unit)
and the `avp cm create` flag path crossing the describe seam."""

from __future__ import annotations

import json

import pytest

from avp.commission import Commission
from avp.descriptor import AgentDescriptor, McpServerDecl, SkillDecl, SubagentDecl, ToolDecl
from avp_cli import cli, library
from avp_cli import commission as commission_mod


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        agent_name="demo",
        agent_version="1.0.0",
        spec_version="0.1",
        default_model="claude-haiku-4-5",
        tools=[ToolDecl(name="Read"), ToolDecl(name="Grep")],
        subagents=[SubagentDecl(name="explorer")],
        skills=[SkillDecl(name="pdf")],
        mcp_servers=[McpServerDecl(id="brain")],
    )


# ── build_commission (unit) ───────────────────────────────────────────────────


def test_build_sets_library_conventions() -> None:
    c = commission_mod.build_commission("my-id", prompt="{input}", model="x/m")
    assert c.schema_version == "0.1"
    assert c.run_id == "my-id"  # run_id is the id, by convention
    assert c.prompt == "{input}" and c.model == "x/m"


def test_clone_carries_bulky_fields_but_resets_run_id() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    base = Commission(
        schema_version="0.1", run_id="old", model="x/m", prompt="p", output_schema=schema
    )
    c = commission_mod.build_commission("new", base=base, prompt="overridden")
    assert c.run_id == "new"  # forced to the new id, not the base's
    assert c.output_schema == schema  # bulky field carried from the clone
    assert c.prompt == "overridden"  # override wins
    assert c.model == "x/m"  # un-overridden base value retained


def test_empty_list_is_a_real_value_expose_none() -> None:
    c = commission_mod.build_commission("x", model="x/m", enabled_builtin_tools=[])
    assert c.enabled_builtin_tools == []  # [] (expose none), not None (expose all)


def test_descriptor_validation_accepts_a_known_subset() -> None:
    c = commission_mod.build_commission(
        "x", model="x/m", enabled_builtin_tools=["Read"], descriptor=_descriptor()
    )
    assert c.enabled_builtin_tools == ["Read"]


def test_descriptor_validation_rejects_an_unknown_tool() -> None:
    with pytest.raises(commission_mod.BuildError, match="no tool 'Bash'"):
        commission_mod.build_commission(
            "x", enabled_builtin_tools=["Bash"], descriptor=_descriptor()
        )


def test_descriptor_validation_checks_mcp_servers_by_id() -> None:
    with pytest.raises(commission_mod.BuildError, match="no MCP server 'ghost'"):
        commission_mod.build_commission(
            "x", enabled_builtin_mcp_servers=["ghost"], descriptor=_descriptor()
        )


# ── avp cm create (CLI seam: create -> describe -> build) ─────────────


@pytest.fixture
def avp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    return tmp_path


def test_create_via_flags_writes_a_wire_commission(avp_home, monkeypatch) -> None:
    # No --agent: no describe, no validation; pure flag build.
    rc = cli.main(["cm", "create", "terse", "--model", "x/m", "--prompt", "{input}"])
    assert rc == 0
    c = library.load("terse")
    assert c.run_id == "terse" and c.model == "x/m" and c.prompt == "{input}"


def test_create_validates_enabled_tools_against_the_agent(avp_home, monkeypatch) -> None:
    # Stub the describe seam so the test is deterministic without an agent binary.
    monkeypatch.setattr(cli, "_describe_for_create", lambda spec: (_descriptor(), None))
    rc = cli.main(
        ["cm", "create", "x", "--agent", "demo", "--enable-tool", "Nope", "--prompt", "p"]
    )
    assert rc == 1  # unknown tool rejected before it could become commission_collision
    assert not library.exists("x")


def test_create_with_valid_enabled_tool_succeeds(avp_home, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_describe_for_create", lambda spec: (_descriptor(), None))
    rc = cli.main(
        [
            "cm",
            "create",
            "x",
            "--agent",
            "demo",
            "--enable-tool",
            "Read",
            "--prompt",
            "p",
            "--model",
            "x/m",
        ]
    )
    assert rc == 0
    assert library.load("x").enabled_builtin_tools == ["Read"]


def test_create_refuses_to_clobber_without_force(avp_home) -> None:
    assert cli.main(["cm", "create", "dup", "--prompt", "a", "--model", "x/m"]) == 0
    assert cli.main(["cm", "create", "dup", "--prompt", "b", "--model", "x/m"]) == 1  # exists
    assert cli.main(["cm", "create", "dup", "--prompt", "b", "--force", "--model", "x/m"]) == 0
    assert library.load("dup").prompt == "b"


def test_create_rejects_a_bad_id(avp_home) -> None:
    assert cli.main(["cm", "create", "Bad Id", "--prompt", "p"]) == 1


def test_create_clone_then_override(avp_home) -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    library.save(
        "src", Commission(schema_version="0.1", run_id="src", model="x/m", output_schema=schema)
    )
    rc = cli.main(["cm", "create", "dst", "--from", "src", "--model", "x/m"])
    assert rc == 0
    dst = library.load("dst")
    assert dst.output_schema == schema and dst.model == "x/m" and dst.run_id == "dst"
    raw = json.loads((avp_home / "commissions" / "dst.json").read_text())
    assert "id" not in raw  # still a pure wire Commission on disk


def test_build_commission_provider_with_credential_handle() -> None:
    c = commission_mod.build_commission(
        "x",
        model="openai/gpt-4o",
        provider_id="openrouter",
        provider_base_url="https://openrouter.ai/api/v1",
        credential="or-key",
    )
    assert c.provider.id == "openrouter"
    assert c.provider.base_url == "https://openrouter.ai/api/v1"
    assert c.provider.credential.vault == "or-key"  # a handle, never the value


def test_build_commission_credential_requires_provider_id() -> None:
    with pytest.raises(commission_mod.BuildError, match="require --provider-id"):
        commission_mod.build_commission("x", model="openai/gpt-4o", credential="or-key")


def test_create_via_flags_with_provider(avp_home) -> None:
    rc = cli.main(
        [
            "cm",
            "create",
            "p",
            "--model",
            "openai/gpt-4o",
            "--provider-id",
            "openrouter",
            "--credential",
            "or-key",
            "--prompt",
            "{input}",
        ]
    )
    assert rc == 0
    c = library.load("p")
    assert c.provider.id == "openrouter" and c.provider.credential.vault == "or-key"
