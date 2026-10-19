"""The managed OpenSandbox control plane: config generation, server reuse vs
spawn, the egress policy every sandbox starts from, and the Docker preflight."""

from __future__ import annotations

import tomllib

import pytest

from avp_cli import osb

# ── config generation ─────────────────────────────────────────────────────────


def test_config_generated_once_with_minted_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    cfg_path = osb._ensure_config()
    cfg = tomllib.loads(cfg_path.read_text())

    assert cfg["server"]["port"] == osb.DEFAULT_PORT
    assert len(cfg["server"]["api_key"]) == 64  # 32 hex bytes, minted per install
    # bind mounts confined to the avp home; nothing else on the host is mountable
    assert cfg["storage"]["allowed_host_paths"] == [str(tmp_path)]
    assert cfg["docker"]["network_mode"] == "bridge"  # required for egress policy
    assert cfg_path.stat().st_mode & 0o777 == 0o600

    # second call: the file is owned by the user now, nothing regenerates
    again = tomllib.loads(osb._ensure_config().read_text())
    assert again["server"]["api_key"] == cfg["server"]["api_key"]


def test_connection_reads_user_edited_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    cfg_path = osb._ensure_config()
    cfg_path.write_text(cfg_path.read_text().replace(f"port = {osb.DEFAULT_PORT}", "port = 9999"))
    conn = osb._connection_from_config(cfg_path)
    assert conn.domain == "127.0.0.1:9999"


# ── ensure_server ─────────────────────────────────────────────────────────────


def test_ensure_server_fails_fast_without_docker(monkeypatch) -> None:
    monkeypatch.setattr(osb, "docker_available", lambda: "Docker is not installed.")
    with pytest.raises(osb.SandboxUnavailable, match="Docker is not installed"):
        osb.ensure_server()


def test_ensure_server_reuses_healthy_server(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    monkeypatch.setattr(osb, "docker_available", lambda: None)
    monkeypatch.setattr(osb, "_healthy", lambda domain: True)
    monkeypatch.setattr(osb, "_key_accepted", lambda conn: True)
    spawned = []
    monkeypatch.setattr(osb, "_spawn_server", lambda: spawned.append(1))

    conn = osb.ensure_server()
    assert spawned == []  # healthy → reused, not respawned
    assert conn.domain == f"127.0.0.1:{osb.DEFAULT_PORT}"
    assert conn.api_key  # key flows from the generated config


def test_ensure_server_spawns_then_waits_for_health(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    monkeypatch.setattr(osb, "docker_available", lambda: None)
    health = iter([False, False, True])  # unhealthy until the spawned server is up
    monkeypatch.setattr(osb, "_healthy", lambda domain: next(health))
    spawned = []
    monkeypatch.setattr(osb, "_spawn_server", lambda: spawned.append(1))

    conn = osb.ensure_server()
    assert spawned == [1]
    assert conn.domain == f"127.0.0.1:{osb.DEFAULT_PORT}"


def test_ensure_server_surfaces_log_tail_on_startup_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    monkeypatch.setattr(osb, "docker_available", lambda: None)
    monkeypatch.setattr(osb, "_healthy", lambda domain: False)
    monkeypatch.setattr(osb, "_spawn_server", lambda: None)
    monkeypatch.setattr(osb, "_HEALTH_TIMEOUT_S", 0.0)
    (tmp_path / "opensandbox").mkdir(parents=True)
    (tmp_path / "opensandbox" / "server.log").write_text("boom: port in use\n")

    with pytest.raises(osb.SandboxUnavailable, match="boom: port in use"):
        osb.ensure_server()


# ── network policy ────────────────────────────────────────────────────────────


def test_network_policy_default_deny_with_provider_domains() -> None:
    policy = osb.network_policy(["internal.example.com", "api.anthropic.com"])
    assert policy.default_action == "deny"
    targets = [r.target for r in policy.egress]
    assert all(r.action == "allow" for r in policy.egress)
    assert "api.anthropic.com" in targets  # provider default
    assert "internal.example.com" in targets  # env addition
    assert targets.count("api.anthropic.com") == 1  # deduped against defaults


# ── stop_server ───────────────────────────────────────────────────────────────


def test_stop_server_handles_missing_and_stale_pidfile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    assert osb.stop_server() is False  # no pidfile

    pid_path = tmp_path / "opensandbox" / "server.pid"
    pid_path.parent.mkdir(parents=True)
    pid_path.write_text("999999999")  # long-dead pid
    assert osb.stop_server() is False
    assert not pid_path.exists()  # stale pidfile cleaned up


def test_a_server_from_another_home_is_reported_not_reused(tmp_path, monkeypatch) -> None:
    # A server started under a different AVP_HOME answers /health but refuses
    # this home's key; reusing it made every sandbox create fail with "invalid
    # credentials". It must be named for what it is instead.
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Other(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(200 if self.path == "/health" else 401)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Other)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    domain = f"127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    monkeypatch.setattr(osb, "docker_available", lambda: None)
    monkeypatch.setattr(
        osb, "_connection_from_config", lambda cfg: osb.Connection(domain=domain, api_key="mine")
    )
    spawned = []
    monkeypatch.setattr(osb, "_spawn_server", lambda: spawned.append(1))
    try:
        with pytest.raises(osb.SandboxUnavailable, match="different AVP_HOME"):
            osb.ensure_server()
    finally:
        server.shutdown()
    assert spawned == []
