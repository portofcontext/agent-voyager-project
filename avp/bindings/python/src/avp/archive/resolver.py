"""avp.resolver — client types for the AVP Resolver API.

Scoped re-exports of the Resolver-API client surface. This module
mirrors the [Resolver API spec](../../../../spec/v0.1/resolver.md).

Consumers building or consuming the Resolver API can:

    from avp.resolver import (
        ResolverDriver,
        HttpResolver,
        http_resolver_from_env,
    )

The classes themselves still live under `avp.agent.*` (the reference
agent's driver-protocol home) — this module is a scoped projection so
adopters can speak Resolver-API only without importing the broader
reference-agent surface.

- `ResolverDriver` — the Protocol all resolver clients implement
  (`resolve(kind, id, ref) -> dict`,
  `spawn_subagent(run_id, id, ref, input) -> SubagentSpawnOutcome`).
- `ResolveError` — exception raised by resolver clients on transport /
  protocol errors.
- `SubagentSpawnOutcome` — result dataclass returned by
  `spawn_subagent`.
- `HttpResolver` — reference HTTP/JSON-RPC client.
- `http_resolver_from_env` — bootstrap helper that reads
  `AVP_RESOLVER_URL` (and optional `AVP_RESOLVER_TOKEN`) and returns an
  `HttpResolver` or `None`.
"""

from __future__ import annotations

from avp.agent.drivers import (
    ResolveError,
    ResolverDriver,
    SubagentSpawnOutcome,
)
from avp.agent.http_resolver import (
    HttpResolver,
    http_resolver_from_env,
)

__all__ = [
    "HttpResolver",
    "ResolveError",
    "ResolverDriver",
    "SubagentSpawnOutcome",
    "http_resolver_from_env",
]
