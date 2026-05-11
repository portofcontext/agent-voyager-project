"""avp-anthropic: AVP v0.1 SDK adapter for the Anthropic Messages API.

The Anthropic Messages API is a raw HTTP client. It ships no agent
loop and no built-in tools. This package is the thin AVP adapter for
that surface:

  - `AnthropicModelDriver` plugs into the reference `avp.agent.AVPAgent`
    as a `ModelDriver`: AVPAgent owns the loop, the driver translates
    each turn between AVP history and the Anthropic Messages API.
  - `AnthropicTracedClient` / `wrap_anthropic` drop AVP tracing into
    an existing Anthropic SDK loop without restructuring around AVPAgent.
  - `build_descriptor` builds an `AgentDescriptor` for the agent that
    USES this SDK (the agent supplies its own tool catalog).
  - `build_anthropic_tools` / `build_anthropic_mcp_servers_from_resolved`
    are Commission-to-API translators.

The agent loop, the tool catalog, the CLI: those belong to the agent
that wraps this SDK. See `python/supervisors/simple-supervisor-example/`
for a reference agent built on top.
"""

from avp_anthropic.descriptor import build_descriptor
from avp_anthropic.discovery import Environment, discover_environment
from avp_anthropic.driver import (
    ANTHROPIC_HOSTED_TOOL_KINDS,
    DEFAULT_PRICES,
    AnthropicModelDriver,
    PriceTable,
    build_anthropic_mcp_servers_from_resolved,
    build_anthropic_tools,
)
from avp_anthropic.traced_client import AnthropicTracedClient, wrap_anthropic

__version__ = "0.1.0"

__all__ = [
    "ANTHROPIC_HOSTED_TOOL_KINDS",
    "DEFAULT_PRICES",
    "AnthropicModelDriver",
    "AnthropicTracedClient",
    "Environment",
    "PriceTable",
    "__version__",
    "build_anthropic_mcp_servers_from_resolved",
    "build_anthropic_tools",
    "build_descriptor",
    "discover_environment",
    "wrap_anthropic",
]
