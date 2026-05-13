"""Tests for managed MCP support in avp-anthropic.

`Commission.mcp_servers[]` carries opaque refs; the AVP resolver protocol
(spec/resolver/v0.1-beta/resolver.md) returns connection material; `AnthropicModelDriver.set_resolved_assets`
translates the material into the Anthropic API's `mcp_servers` connector
parameter for subsequent `messages.create(...)` calls.

These tests pin:
  - `build_anthropic_mcp_servers_from_resolved` produces the API
    connector shape from resolved material.
  - `AnthropicModelDriver.set_resolved_assets` populates
    `driver.mcp_servers_param` from the resolved material.
  - HTTP-only restriction: stdio entries are skipped with a warning
    (Anthropic's API connector doesn't speak stdio).
  - Bearer-token auth: `auth.token` in resolved material → API connector
    `authorization_token` field.
"""

from __future__ import annotations

import warnings

from avp_anthropic import (
    AnthropicModelDriver,
    build_anthropic_mcp_servers_from_resolved,
)


def test_resolved_http_server_becomes_url_connector_entry() -> None:
    resolved = {
        "github": {
            "transport": "http",
            "url": "https://mcp.github.com/",
        }
    }
    out = build_anthropic_mcp_servers_from_resolved(resolved)
    assert out == [{"type": "url", "name": "github", "url": "https://mcp.github.com/"}]


def test_resolved_http_server_with_bearer_auth_attaches_token() -> None:
    resolved = {
        "github": {
            "transport": "http",
            "url": "https://mcp.github.com/",
            "auth": {"token": "secret-xyz"},
        }
    }
    out = build_anthropic_mcp_servers_from_resolved(resolved)
    assert out[0]["authorization_token"] == "secret-xyz"


def test_resolved_stdio_server_is_skipped_with_warning() -> None:
    resolved = {
        "fs": {
            "transport": "stdio",
            "command": ["npx", "-y", "mcp-server-fs"],
        }
    }
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = build_anthropic_mcp_servers_from_resolved(resolved)
    assert out == []
    assert any("stdio" in str(w.message).lower() for w in caught)


def test_set_resolved_assets_populates_driver_mcp_servers_param() -> None:
    """AVPAgent calls `driver.set_resolved_assets(...)` after `avp.resolve`
    returns; the driver stages the resolved MCP material for the next
    `messages.create(...)` call."""
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=object())
    assert driver.mcp_servers_param is None
    driver.set_resolved_assets(
        mcp_servers={
            "github": {"transport": "http", "url": "https://mcp.github.com/"},
        }
    )
    assert driver.mcp_servers_param == [
        {"type": "url", "name": "github", "url": "https://mcp.github.com/"}
    ]


def test_set_resolved_assets_merges_with_preexisting_mcp_servers_param() -> None:
    """A caller that pre-populates `mcp_servers_param` at construction
    time doesn't lose those entries when AVPAgent calls
    `set_resolved_assets` with new resolved material."""
    driver = AnthropicModelDriver(
        model="claude-sonnet-4-6",
        client=object(),
        mcp_servers_param=[{"type": "url", "name": "preexisting", "url": "https://x.example.com"}],
    )
    driver.set_resolved_assets(
        mcp_servers={
            "github": {"transport": "http", "url": "https://mcp.github.com/"},
        }
    )
    names = [entry["name"] for entry in driver.mcp_servers_param]
    assert names == ["preexisting", "github"]


def test_set_resolved_assets_exposes_resolved_subagents_as_tools() -> None:
    """A managed subagent must surface on `tools_param` after resolution
    so the model can invoke it by name. Without this exposure, AVPAgent's
    subagent dispatch path never fires — the model never *learns* the
    subagent exists."""
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=object())
    assert driver.tools_param is None
    driver.set_resolved_assets(
        mcp_servers={},
        subagents={
            "summarizer": {
                "name": "summarizer",
                "description": "Compresses a passage into 2 bullets.",
            }
        },
    )
    assert driver.tools_param is not None
    names = [t["name"] for t in driver.tools_param]
    assert names == ["summarizer"]
    sa = driver.tools_param[0]
    assert sa["description"] == "Compresses a passage into 2 bullets."
    assert sa["input_schema"]["type"] == "object"
    assert "prompt" in sa["input_schema"]["properties"]


def test_set_resolved_assets_appends_subagents_to_existing_tools() -> None:
    """Pre-populated `tools_param` (built-ins) is preserved when the
    resolver adds subagents — append-merge, no clobber."""
    driver = AnthropicModelDriver(
        model="claude-sonnet-4-6",
        client=object(),
        tools_param=[{"name": "read_file", "input_schema": {"type": "object"}}],
    )
    driver.set_resolved_assets(
        mcp_servers={},
        subagents={"summarizer": {"name": "summarizer", "description": "x"}},
    )
    names = [t["name"] for t in driver.tools_param]
    assert names == ["read_file", "summarizer"]
