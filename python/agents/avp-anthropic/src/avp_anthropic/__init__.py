"""avp-anthropic — AVP v0.1 agent for the Anthropic Messages API.

Driver pattern: this package's `AnthropicModelDriver` plugs into the reference
`avp.agent.AVPAgent`. The agent owns the agent loop; the driver translates
each turn's request/response between AVP shape and Anthropic shape.
"""

from avp_anthropic.discovery import Environment, discover_environment
from avp_anthropic.driver import (
    ANTHROPIC_HOSTED_TOOL_KINDS,
    DEFAULT_PRICES,
    AnthropicModelDriver,
    PriceTable,
    build_anthropic_mcp_servers,
    build_anthropic_tools,
)
from avp_anthropic.manifest import manifest
from avp_anthropic.shell_tools import SHELL_TOOL_NAMES, SHELL_TOOL_SCHEMAS
from avp_anthropic.traced_client import AnthropicTracedClient, wrap_anthropic

__version__ = "0.1.0"

__all__ = [
    "ANTHROPIC_HOSTED_TOOL_KINDS",
    "DEFAULT_PRICES",
    "SHELL_TOOL_NAMES",
    "SHELL_TOOL_SCHEMAS",
    "AnthropicModelDriver",
    "AnthropicTracedClient",
    "Environment",
    "PriceTable",
    "__version__",
    "build_anthropic_mcp_servers",
    "build_anthropic_tools",
    "discover_environment",
    "manifest",
    "wrap_anthropic",
]
