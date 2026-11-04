"""The hosts a run's sandbox may reach."""

from typing import Any

from avp.commission import Commission
from avp_cli.runs import network


def commission(**fields: Any) -> Commission:
    return Commission.model_validate(
        {
            "avp_version": "0.1",
            "run_id": "r",
            "prompt": "hi",
            "model": {"provider": "anthropic", "id": "m"},
            **fields,
        }
    )


def test_model_host_defaults_to_the_providers_base_url() -> None:
    assert network.allowed_hosts(commission(), []) == {"api.anthropic.com": ["model"]}


def test_model_base_url_wins() -> None:
    model = {"provider": "anthropic", "id": "m", "base_url": "https://gateway.example.com/v1"}
    assert network.allowed_hosts(commission(model=model), []) == {"gateway.example.com": ["model"]}


def test_unknown_provider_has_no_model_host() -> None:
    model = {"provider": "nobody-knows", "id": "m"}
    assert network.allowed_hosts(commission(model=model), ["x.example.com"]) == {
        "x.example.com": ["--allow-host"]
    }


def test_http_mcp_servers_and_allow_host_are_added_once() -> None:
    servers = [
        {"id": "web", "name": "Web", "type": "http", "url": "https://mcp.example.com/mcp"},
        {"id": "local", "name": "Local", "type": "stdio", "command": ["local-mcp"]},
    ]
    hosts = network.allowed_hosts(
        commission(mcp_servers=servers), ["mcp.example.com", "api.anthropic.com", "pypi.org"]
    )
    assert hosts == {
        "api.anthropic.com": ["model", "--allow-host"],
        "mcp.example.com": ["MCP server web", "--allow-host"],
        "pypi.org": ["--allow-host"],
    }
    assert network.describe(hosts) == (
        "api.anthropic.com (model, --allow-host), "
        "mcp.example.com (MCP server web, --allow-host), pypi.org (--allow-host)"
    )
