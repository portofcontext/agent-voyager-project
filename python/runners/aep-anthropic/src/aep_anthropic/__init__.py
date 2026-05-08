"""aep-anthropic — AEP v0.1 runner for the Anthropic Messages API.

Driver pattern: this package's `AnthropicModelDriver` plugs into the reference
`aep.runner.AEPRunner`. The runner owns the agent loop; the driver translates
each turn's request/response between AEP shape and Anthropic shape.
"""

from aep_anthropic.discovery import Environment, discover_environment
from aep_anthropic.driver import (
    ANTHROPIC_HOSTED_TOOL_KINDS,
    DEFAULT_PRICES,
    AnthropicModelDriver,
    PriceTable,
    build_anthropic_mcp_servers,
    build_anthropic_tools,
)
from aep_anthropic.shell_tools import SHELL_TOOL_NAMES, SHELL_TOOL_SCHEMAS
from aep_anthropic.traced_client import AnthropicTracedClient, wrap_anthropic

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
    "wrap_anthropic",
]
