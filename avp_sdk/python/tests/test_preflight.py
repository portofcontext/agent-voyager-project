import pytest

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.utils.preflight import check_commission

DESCRIPTOR = AgentDescriptor.model_validate(
    {
        "avp_version": "0.1",
        "agent_name": "demo",
        "agent_version": "1.2.0",
        "tools": [
            {"name": "bash", "inputSchema": {"type": "object"}},
            {"name": "search", "inputSchema": {"type": "object"}, "mcp_server_id": "web"},
        ],
        "mcp_servers": [{"id": "web"}],
        "skills": [{"name": "review", "description": "Reviews code."}],
        "subagents": [{"name": "explorer"}],
    }
)


def skill(name: str, skill_md: str) -> dict:
    return {"name": name, "files": {"SKILL.md": skill_md}}


def commission(**fields) -> Commission:
    return Commission.model_validate(
        {
            "avp_version": "0.1",
            "run_id": "run-1",
            "model": {"provider": "anthropic", "id": "claude-sonnet-4-5"},
            "prompt": "Fix the bug.",
            **fields,
        }
    )


def refusal(commission: Commission) -> str:
    message = check_commission(commission, DESCRIPTOR)
    assert message is not None
    return message


def test_a_plain_commission_passes():
    assert check_commission(commission(), DESCRIPTOR) is None


def test_agents_without_an_entry_for_this_agent():
    assert "no entry for 'demo'" in refusal(commission(agents={"other": {}}))
    assert check_commission(commission(agents={"demo": {}}), DESCRIPTOR) is None


def test_a_different_version():
    assert "1.1.0" in refusal(commission(agents={"demo": {"version": "1.1.0"}}))
    assert check_commission(commission(agents={"demo": {"version": "1.2.0"}}), DESCRIPTOR) is None


@pytest.mark.parametrize(
    ("field", "known", "unknown"),
    [
        ("enabled_tools", "bash", "search"),  # search comes from an MCP server
        ("enabled_subagents", "explorer", "planner"),
        ("enabled_skills", "review", "deploy"),
        ("enabled_mcp_servers", "web", "db"),
    ],
)
def test_enabled_lists_name_only_items_the_agent_has(field, known, unknown):
    assert check_commission(commission(agents={"demo": {field: [known]}}), DESCRIPTOR) is None
    message = refusal(commission(agents={"demo": {field: [known, unknown]}}))
    assert field in message and unknown in message


@pytest.mark.parametrize(
    "skill_md",
    [
        "---\nname: lint\ndescription: Lints.\n---\nBody",
        '---\nname: "lint"\n---\n',
        "---\r\nname: 'lint'\r\n---\r\n",
        "---\nname: lint # the linter\n---\n",
    ],
)
def test_skill_name_matches_its_frontmatter(skill_md):
    assert check_commission(commission(skills=[skill("lint", skill_md)]), DESCRIPTOR) is None


@pytest.mark.parametrize(
    ("skill_md", "found"),
    [
        ("---\nname: linter\n---\n", "names 'linter'"),
        ("---\ndescription: Lints.\n---\n", "has no name"),
        ("name: lint\n", "has no name"),
        ("---\nmetadata:\n  name: lint\n---\n", "has no name"),
    ],
)
def test_skill_name_differs_from_its_frontmatter(skill_md, found):
    assert found in refusal(commission(skills=[skill("lint", skill_md)]))


def test_added_items_that_clash_with_built_in_ones():
    server = {"id": "web", "type": "http", "url": "https://example.com/mcp"}
    assert "'web'" in refusal(commission(mcp_servers=[server]))
    review = skill("review", "---\nname: review\n---\n")
    assert "'review'" in refusal(commission(skills=[review]))
