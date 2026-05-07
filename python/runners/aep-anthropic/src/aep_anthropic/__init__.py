"""aep-anthropic — AEP v0.1 runner for the Anthropic Messages API.

Driver pattern: this package's `AnthropicModelDriver` plugs into the reference
`aep.runner.AEPRunner`. The runner owns the agent loop; the driver translates
each turn's request/response between AEP shape and Anthropic shape.
"""

from aep_anthropic.driver import (
    DEFAULT_PRICES,
    AnthropicModelDriver,
    PriceTable,
    build_anthropic_tools,
)
from aep_anthropic.traced_client import AnthropicTracedClient, wrap_anthropic

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_PRICES",
    "AnthropicModelDriver",
    "AnthropicTracedClient",
    "PriceTable",
    "__version__",
    "build_anthropic_tools",
    "wrap_anthropic",
]
