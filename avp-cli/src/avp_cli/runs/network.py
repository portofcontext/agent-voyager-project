"""The hosts a run's sandbox may reach. Everything else is denied.

- The model's host: from `model.base_url`, or else the SDK's bundled default
  base URL for `model.provider`.
- Each HTTP MCP server's host. A stdio server runs in the sandbox.
- Each `--allow-host`, added to the others.

The hosts an agent needs on its own, such as its built-in remote MCP servers,
aren't known yet; see "Open: the hosts an agent needs" in tmp-migration.md.
"""

from urllib.parse import urlparse

from avp.commission import Commission, McpServerHttp
from avp.utils.endpoints import bundled_endpoints, default_base_url

MODEL = "model"
ALLOW_HOST = "--allow-host"


def allowed_hosts(commission: Commission, allow_host: list[str]) -> dict[str, list[str]]:
    """Each allowed host, with why. Keyed by host, so each appears once."""
    hosts: dict[str, list[str]] = {}

    def add(host: str | None, reason: str) -> None:
        if host:
            reasons = hosts.setdefault(host, [])
            if reason not in reasons:
                reasons.append(reason)

    base_url = model_url(commission)
    add(urlparse(base_url).hostname if base_url else None, MODEL)
    for server in commission.mcp_servers or []:
        if isinstance(server, McpServerHttp):
            add(urlparse(server.url).hostname, f"MCP server {server.id}")
    for host in allow_host:
        add(host, ALLOW_HOST)
    return hosts


def model_url(commission: Commission) -> str | None:
    """`model.base_url`, or else the SDK's bundled default for the provider."""
    model = commission.model
    return model.base_url or default_base_url(bundled_endpoints(), model.provider)


def describe(hosts: dict[str, list[str]]) -> str:
    if not hosts:
        return "none"
    return ", ".join(f"{host} ({', '.join(reasons)})" for host, reasons in hosts.items())
