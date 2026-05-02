"""aep-anthropic — AEP v0.1 runner for the Anthropic Messages API.

Driver pattern: this package's `AnthropicModelDriver` plugs into the reference
`aep.runner.AEPRunner`. The runner owns the agent loop; the driver translates
each turn's request/response between AEP shape and Anthropic shape.
"""

from aep_anthropic.driver import (
    DEFAULT_PRICES,
    AnthropicModelDriver,
    PriceTable,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_PRICES",
    "AnthropicModelDriver",
    "PriceTable",
    "__version__",
]
