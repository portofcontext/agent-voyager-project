"""Generating commissions into the library: `commission.build_commission` (unit)
and the `avp cm create` generator path crossing the describe seam."""

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
    c = commission_mod.build_commission("my-id", model="x/m")
    assert c.schema_version == "0.1"
    assert c.run_id == "my-id"  # run_id is the id, by convention
    assert c.model == "x/m"
    assert "{input}" in c.prompt  # the generated sample prompt is eval-ready


def test_clone_carries_bulky_fields_but_resets_run_id() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    base = Commission(
        schema_version="0.1", run_id="old", model="x/m", prompt="p", output_schema=schema
    )
    c = commission_mod.build_commission("new", base=base)
    assert c.run_id == "new"  # forced to the new id, not the base's
    assert c.output_schema == schema  # bulky field carried from the clone
    assert c.prompt == "p"  # base values retained
    assert c.model == "x/m"


def test_generation_enumerates_the_full_surface_per_agent() -> None:
    c = commission_mod.build_commission("x", descriptor=_descriptor())
    assert c.enabled_builtin_tools == {"demo": ["Read", "Grep"]}
    assert c.enabled_builtin_subagents == {"demo": ["explorer"]}
    assert c.enabled_builtin_skills == {"demo": ["pdf"]}
    assert c.enabled_builtin_mcp_servers == {"demo": ["brain"]}
    assert c.agent_versions == {"demo": "1.0.0"}  # pinned at the described build
    # default_model "claude-haiku-4-5" is not a canonical slug -> sample model
    assert c.model == commission_mod.SAMPLE_MODEL


def test_generation_omits_categories_the_agent_lacks() -> None:
    bare = AgentDescriptor(
        agent_name="tiny",
        agent_version="0.1.0",
        spec_version="0.1",
        tools=[ToolDecl(name="Read")],
    )
    c = commission_mod.build_commission("x", descriptor=bare)
    assert c.enabled_builtin_tools == {"tiny": ["Read"]}
    # No subagents/skills/MCP advertised: fields stay None (expose-all default),
    # never {agent: []} (which would mean expose NONE).
    assert c.enabled_builtin_subagents is None
    assert c.enabled_builtin_skills is None
    assert c.enabled_builtin_mcp_servers is None


def test_slug_default_model_is_used_when_canonical() -> None:
    d = _descriptor().model_copy(update={"default_model": "anthropic/claude-opus-4-8"})
    c = commission_mod.build_commission("x", descriptor=d)
    assert c.model == "anthropic/claude-opus-4-8"


def test_descriptor_validation_rejects_an_unknown_tool_in_my_key() -> None:
    base = Commission(
        schema_version="0.1",
        run_id="b",
        model="x/m",
        prompt="p",
        enabled_builtin_tools={"demo": ["Bash"]},
    )
    with pytest.raises(commission_mod.BuildError, match="no tool 'Bash'"):
        commission_mod.build_commission("x", base=base, descriptor=_descriptor())


def test_descriptor_validation_ignores_other_agents_keys() -> None:
    base = Commission(
        schema_version="0.1",
        run_id="b",
        model="x/m",
        prompt="p",
        enabled_builtin_tools={"demo": ["Read"], "someone-else": ["whatever"]},
    )
    c = commission_mod.build_commission("x", base=base, descriptor=_descriptor())
    assert c.enabled_builtin_tools["someone-else"] == ["whatever"]  # not ours to judge


# ── avp cm create (CLI seam: create -> describe -> generate) ─────────────


@pytest.fixture
def avp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    return tmp_path


def test_create_without_agent_writes_a_minimal_runnable_commission(avp_home) -> None:
    rc = cli.main(["cm", "create", "terse", "--model", "x/m"])
    assert rc == 0
    c = library.load("terse")
    assert c.run_id == "terse" and c.model == "x/m"
    assert "{input}" in c.prompt  # never a blank-field crash: sample prompt fills in


def test_create_with_agent_generates_the_full_surface(avp_home, monkeypatch) -> None:
    # Stub the describe seam so the test is deterministic without an agent binary.
    monkeypatch.setattr(cli, "_describe_for_create", lambda spec: (_descriptor(), None))
    rc = cli.main(["cm", "create", "x", "--agent", "demo"])
    assert rc == 0
    c = library.load("x")
    assert c.enabled_builtin_tools == {"demo": ["Read", "Grep"]}
    assert c.agent_versions == {"demo": "1.0.0"}


def test_create_fails_loudly_when_describe_fails(avp_home, monkeypatch) -> None:
    monkeypatch.setattr(cli, "_describe_for_create", lambda spec: (None, "boom"))
    rc = cli.main(["cm", "create", "x", "--agent", "demo"])
    assert rc == 1  # generation needs the real surface; no partial guess-file
    assert not library.exists("x")


def test_create_refuses_to_clobber_without_force(avp_home) -> None:
    assert cli.main(["cm", "create", "dup", "--model", "x/m"]) == 0
    assert cli.main(["cm", "create", "dup", "--model", "y/m"]) == 1  # exists
    assert cli.main(["cm", "create", "dup", "--model", "y/m", "--force"]) == 0
    assert library.load("dup").model == "y/m"


def test_create_rejects_a_bad_id(avp_home) -> None:
    assert cli.main(["cm", "create", "Bad Id"]) == 1


def test_create_clone_then_override(avp_home) -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    library.save(
        "src", Commission(schema_version="0.1", run_id="src", model="x/m", output_schema=schema)
    )
    rc = cli.main(["cm", "create", "dst", "--from", "src"])
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


def test_create_with_provider(avp_home) -> None:
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
        ]
    )
    assert rc == 0
    c = library.load("p")
    assert c.provider.id == "openrouter" and c.provider.credential.vault == "or-key"
