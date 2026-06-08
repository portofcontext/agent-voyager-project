"""Vault resolution + the broker that keeps secrets out of the sandbox.

Covers: handle → value resolution (env, file, miss); the broker's
credential-injection + routing against a fake upstream; and the run wiring
(broker routes built from a Commission, sentinel-only sandbox env, broker urls
in the written commission, broker-mode egress) that together realize the vault
guarantee — the agent uses a credential it can never read.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from avp.commission import Commission, McpServerHttp, Provider, SecretRef
from avp_cli import agent, broker, vault

# ── vault resolution ─────────────────────────────────────────────────────────


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


def test_store_list_resolve_remove_round_trip(tmp_path, monkeypatch) -> None:
    import stat

    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    for k in ("AVP_VAULT_OPENROUTER", "AVP_VAULT_MOT"):
        monkeypatch.delenv(k, raising=False)
    vault.store("openrouter", 'sk-or-with-"quote"-and-\\slash')
    vault.store("mot", "tok")
    assert vault.names() == ["mot", "openrouter"]
    assert stat.S_IMODE(vault.secrets_path().stat().st_mode) == 0o600
    # value with quotes/backslashes round-trips through the TOML writer
    assert vault.resolve("openrouter") == 'sk-or-with-"quote"-and-\\slash'
    assert vault.remove("mot") is True
    assert vault.remove("mot") is False
    assert vault.names() == ["openrouter"]


def test_store_rejects_invalid_handle(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    with pytest.raises(vault.VaultError, match="invalid handle"):
        vault.store("Bad Handle", "x")
    with pytest.raises(vault.VaultError, match="empty value"):
        vault.store("ok", "")


# ── broker: injection + routing ──────────────────────────────────────────────


@pytest.fixture
def fake_upstream():
    """An upstream that echoes the auth headers + path it received."""
    seen: dict[str, object] = {}

    class U(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _echo(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            seen["path"] = self.path
            seen["authorization"] = self.headers.get("authorization")
            seen["x-api-key"] = self.headers.get("x-api-key")
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _echo

    srv = ThreadingHTTPServer(("127.0.0.1", 0), U)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", seen
    srv.shutdown()


def test_broker_overwrites_sentinel_with_real_secret(fake_upstream) -> None:
    origin, seen = fake_upstream
    brk = broker.Broker()
    brk.add_route(
        "llm/openrouter",
        broker.Route(upstream=origin, header="authorization", prefix="Bearer ", secret="REAL"),
    )
    brk.start()
    try:
        c = httpx.Client()
        # The agent sends a sentinel; the broker must replace it with the real key.
        r = c.post(
            f"http://127.0.0.1:{brk.port}/llm/openrouter/api/v1/chat",
            headers={"authorization": "Bearer avp-vault-managed"},
            json={"x": 1},
        )
        assert r.status_code == 200
        assert seen["authorization"] == "Bearer REAL"  # real key reached upstream
        assert seen["path"] == "/api/v1/chat"  # path remainder preserved
    finally:
        brk.stop()


def test_broker_anthropic_uses_x_api_key(fake_upstream) -> None:
    origin, seen = fake_upstream
    brk = broker.Broker()
    brk.add_route(
        "llm/anthropic", broker.Route(upstream=origin, header="x-api-key", prefix="", secret="ANT")
    )
    brk.start()
    try:
        httpx.Client().post(
            f"http://127.0.0.1:{brk.port}/llm/anthropic/v1/messages",
            headers={"x-api-key": "avp-vault-managed"},
            json={"x": 1},
        )
        assert seen["x-api-key"] == "ANT"
    finally:
        brk.stop()


def test_broker_preserves_gzip_response() -> None:
    """The broker forwards the body raw (iter_raw), so it must keep
    `content-encoding` — else a client that requested gzip (e.g. the Anthropic
    SDK) gets compressed bytes labeled plaintext and fails to parse."""
    import gzip as _gzip

    payload = b'{"ok":true,"msg":"PONG"}'

    class U(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            body = _gzip.compress(payload)
            self.send_response(200)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), U)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{srv.server_address[1]}"
    brk = broker.Broker()
    brk.add_route("llm/x", broker.Route(upstream=origin, header="x-api-key", prefix="", secret="K"))
    brk.start()
    try:
        # httpx auto-decodes gzip when content-encoding is present and intact.
        r = httpx.Client().post(f"http://127.0.0.1:{brk.port}/llm/x/v1", json={"a": 1})
        assert r.json()["msg"] == "PONG"
    finally:
        brk.stop()
        srv.shutdown()


def test_broker_refuses_unrouted_destination() -> None:
    brk = broker.Broker()
    brk.start()
    try:
        r = httpx.Client().get(f"http://127.0.0.1:{brk.port}/llm/ghost/x")
        assert r.status_code == 404  # only commission-declared upstreams are reachable
        assert httpx.Client().get(f"http://127.0.0.1:{brk.port}/health").text == "ok"
    finally:
        brk.stop()


# ── run wiring ───────────────────────────────────────────────────────────────


class _Agent:
    env: dict[str, str] = {}
    image = "x"
    command: list[str] = []


def _commission(**kw) -> Commission:
    base = {"schema_version": "0.1", "run_id": "r", "model": "openai/gpt-4o"}
    base.update(kw)
    return Commission(**base)


def test_start_broker_builds_routes_and_resolves_handles(monkeypatch) -> None:
    monkeypatch.setenv("AVP_VAULT_OPENROUTER", "sk-or-REAL")
    monkeypatch.setenv("AVP_VAULT_MOT", "tok-REAL")
    c = _commission(
        provider=Provider(
            id="openrouter",
            base_url="https://openrouter.ai/api/v1",
            credential=SecretRef(vault="openrouter"),
        ),
        mcp_servers=[
            McpServerHttp(id="net", type="http", url="https://x/mcp", auth=SecretRef(vault="mot"))
        ],
    )
    brk = agent._start_broker(c)
    assert brk is not None
    try:
        assert "/llm/openrouter" in brk.route_url("llm/openrouter")
        assert "/mcp/net" in brk.route_url("mcp/net")
    finally:
        brk.stop()


def test_start_broker_none_without_secrets() -> None:
    # No provider credential, no MCP auth → no secret → no broker needed.
    c = _commission(mcp_servers=[McpServerHttp(id="net", type="http", url="https://x/mcp")])
    assert agent._start_broker(c) is None


def test_sandbox_env_broker_mode_is_sentinel_only(monkeypatch) -> None:
    monkeypatch.setenv("AVP_VAULT_OPENROUTER", "sk-or-REAL")
    c = _commission(
        provider=Provider(
            id="openrouter",
            base_url="https://openrouter.ai/api/v1",
            credential=SecretRef(vault="openrouter"),
        )
    )
    brk = agent._start_broker(c)
    try:
        env = agent._sandbox_env(_Agent, c, brk)
        assert env["OPENROUTER_API_KEY"] == agent._VAULT_SENTINEL
        assert env["OPENROUTER_HOST"] == brk.route_url("llm/openrouter")
        assert env["GOOSE_PROVIDER"] == "openrouter"
        assert not any("sk-or-REAL" in v for v in env.values())  # real key never in sandbox env
    finally:
        brk.stop()


def test_written_commission_has_broker_urls_no_secret(monkeypatch) -> None:
    monkeypatch.setenv("AVP_VAULT_OPENROUTER", "sk-or-REAL")
    monkeypatch.setenv("AVP_VAULT_MOT", "tok-REAL")
    c = _commission(
        provider=Provider(id="openrouter", credential=SecretRef(vault="openrouter")),
        mcp_servers=[
            McpServerHttp(id="net", type="http", url="https://x/mcp", auth=SecretRef(vault="mot"))
        ],
    )
    brk = agent._start_broker(c)
    try:
        written = agent._commission_for_sandbox(c, brk)
        data = json.loads(written)
        server = data["mcp_servers"][0]
        assert server["url"] == brk.route_url("mcp/net")  # rewritten to broker
        assert "auth" not in server  # broker injects it; handle not needed in-sandbox
        # provider + auth are supervisor concerns delivered via env, and released
        # agents reject unknown fields — so neither appears in what the agent reads.
        assert "provider" not in data
        assert "sk-or-REAL" not in written and "tok-REAL" not in written
    finally:
        brk.stop()


def test_egress_broker_mode_is_host_alias_only(monkeypatch) -> None:
    monkeypatch.setenv("AVP_VAULT_OPENROUTER", "sk-or-REAL")
    monkeypatch.setenv("AVP_VAULT_MOT", "tok-REAL")
    c = _commission(
        provider=Provider(
            id="openrouter",
            base_url="https://openrouter.ai/api/v1",
            credential=SecretRef(vault="openrouter"),
        ),
        mcp_servers=[
            McpServerHttp(
                id="net",
                type="http",
                url="https://network.motiveos.ai/mcp",
                auth=SecretRef(vault="mot"),
            )
        ],
    )
    brk = agent._start_broker(c)
    try:
        # Both endpoints are brokered, so the sandbox only needs the broker host;
        # it never talks to openrouter.ai / motiveos.ai directly.
        assert agent._egress_extra(c, brk) == [broker.SANDBOX_HOST_ALIAS]
    finally:
        brk.stop()


def test_egress_non_brokered_endpoints_stay_direct() -> None:
    # No secrets → no broker → provider + MCP hosts must be in the allowlist.
    c = _commission(
        provider=Provider(id="openrouter", base_url="https://openrouter.ai/api/v1"),
        mcp_servers=[McpServerHttp(id="net", type="http", url="https://network.motiveos.ai/mcp")],
    )
    hosts = agent._egress_extra(c, None)
    assert "openrouter.ai" in hosts and "network.motiveos.ai" in hosts


def test_serialized_commission_carries_handles_not_values(monkeypatch) -> None:
    """The wire guarantee (independent of the broker): a serialized Commission
    shows vault handles, never the resolved secret."""
    monkeypatch.setenv("AVP_VAULT_MOTIVEOS", "super-secret")
    c = _commission(
        model="anthropic/claude-opus-4-8",
        provider=Provider(id="anthropic", credential=SecretRef(vault="anthro")),
        mcp_servers=[
            McpServerHttp(
                id="net", type="http", url="https://x/mcp", auth=SecretRef(vault="motiveos")
            )
        ],
    )
    wire = c.model_dump_json(by_alias=True, exclude_none=True)
    assert "super-secret" not in wire
    assert '"vault":"motiveos"' in wire.replace(" ", "")
