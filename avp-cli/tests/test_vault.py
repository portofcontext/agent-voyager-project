"""Vault resolution + the supervisor-side secret-handling guarantees.

Covers: handle → value resolution (env, file, miss); the per-run secret env the
CLI injects from a Commission; egress derived from a Commission; and the wire
guarantee that the Commission a supervisor serializes carries only handles, so
a resolved secret value never reaches the trajectory snapshot.
"""

from __future__ import annotations

import pytest

from avp.commission import Commission, McpServerHttp, Provider, SecretRef
from avp_cli import osb, vault
from avp_cli.agent import _commission_secret_env


def test_resolve_prefers_env_then_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    monkeypatch.setenv("AVP_VAULT_OPENROUTER", "sk-or-from-env")
    assert vault.resolve("openrouter") == "sk-or-from-env"


def test_resolve_falls_back_to_secrets_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    monkeypatch.delenv("AVP_VAULT_MOTIVEOS", raising=False)
    (tmp_path / "secrets.toml").write_text('[secrets]\nmotiveos = "tok-from-file"\n')
    assert vault.resolve("motiveos") == "tok-from-file"


def test_resolve_unknown_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    monkeypatch.delenv("AVP_VAULT_NOPE", raising=False)
    with pytest.raises(vault.VaultError, match="nope"):
        vault.resolve("nope")


def test_secret_env_provider_anthropic(monkeypatch) -> None:
    monkeypatch.setenv("AVP_VAULT_ANTHRO", "sk-ant-x")
    c = Commission(
        schema_version="0.1",
        run_id="r",
        model="anthropic/claude-opus-4-8",
        provider=Provider(
            id="anthropic", base_url="https://gw.example/v1", credential=SecretRef(vault="anthro")
        ),
    )
    env = _commission_secret_env(c)
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-x"
    assert env["ANTHROPIC_BASE_URL"] == "https://gw.example/v1"


def test_secret_env_provider_gateway_and_mcp(monkeypatch) -> None:
    monkeypatch.setenv("AVP_VAULT_OPENROUTER", "sk-or-y")
    monkeypatch.setenv("AVP_VAULT_MOTIVEOS", "tok-z")
    c = Commission(
        schema_version="0.1",
        run_id="r",
        model="openai/gpt-4o",
        provider=Provider(
            id="openrouter",
            base_url="https://openrouter.ai/api/v1",
            credential=SecretRef(vault="openrouter"),
        ),
        mcp_servers=[
            McpServerHttp(
                id="net", type="http", url="https://x/mcp", auth=SecretRef(vault="motiveos")
            )
        ],
    )
    env = _commission_secret_env(c)
    assert env["OPENROUTER_API_KEY"] == "sk-or-y"
    assert env["OPENROUTER_HOST"] == "https://openrouter.ai/api/v1"
    # MCP auth → deterministic AVP_VAULT_<HANDLE> the agent resolves at dial time.
    assert env["AVP_VAULT_MOTIVEOS"] == "tok-z"


def test_egress_derived_from_commission() -> None:
    c = Commission(
        schema_version="0.1",
        run_id="r",
        model="openai/gpt-4o",
        provider=Provider(id="openrouter", base_url="https://openrouter.ai/api/v1"),
        mcp_servers=[McpServerHttp(id="net", type="http", url="https://network.motiveos.ai/mcp")],
    )
    hosts = osb.commission_egress_hosts(c)
    assert "openrouter.ai" in hosts
    assert "network.motiveos.ai" in hosts


def test_egress_native_default_uses_slug_origin() -> None:
    c = Commission(schema_version="0.1", run_id="r", model="anthropic/claude-opus-4-8")
    assert osb.commission_egress_hosts(c) == ["api.anthropic.com"]


def test_serialized_commission_carries_handles_not_values(monkeypatch) -> None:
    """The wire guarantee: a serialized Commission shows vault handles, never the
    resolved secret. This is what keeps the value out of the run_requested
    snapshot the agent emits."""
    monkeypatch.setenv("AVP_VAULT_MOTIVEOS", "super-secret-token")
    c = Commission(
        schema_version="0.1",
        run_id="r",
        model="anthropic/claude-opus-4-8",
        provider=Provider(id="anthropic", credential=SecretRef(vault="anthro")),
        mcp_servers=[
            McpServerHttp(
                id="net", type="http", url="https://x/mcp", auth=SecretRef(vault="motiveos")
            )
        ],
    )
    wire = c.model_dump_json(by_alias=True, exclude_none=True)
    assert "super-secret-token" not in wire
    assert '"vault":"motiveos"' in wire.replace(" ", "")
    assert '"vault":"anthro"' in wire.replace(" ", "")
