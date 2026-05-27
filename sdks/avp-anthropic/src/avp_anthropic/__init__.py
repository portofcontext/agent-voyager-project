"""avp-anthropic: AVP v0.1 SDK adapter for the Anthropic Messages API.

The Anthropic Messages API is a raw HTTP client. It ships no agent
loop and no built-in tools. This package is the thin AVP adapter for
that surface:

  - `AnthropicModelDriver` is a per-turn translator: an agent loop calls
    `.step(history)` and emits the matching `avp.trajectory` events. The
    driver ships no loop and no tools (the API has neither).
  - `AnthropicTracedClient` / `wrap_anthropic` drop AVP tracing into an
    existing Anthropic SDK loop the caller owns, emitting one
    `assistant_message` per `messages.create(...)`.
  - `build_descriptor` builds an `AgentDescriptor` for the agent that
    USES this SDK (the agent supplies its own tool catalog).
  - `build_anthropic_tools` / `build_anthropic_mcp_servers_from_resolved`
    are Commission-to-API translators.
  - `model_response_to_content` / `model_response_usage` turn a
    `ModelResponse` into `assistant_message` content / usage (shared by the
    reference agent and the traced client).

The agent loop, the tool catalog, the CLI: those belong to the agent
that wraps this SDK. See `supervisors/simple-supervisor-example/`
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
from avp_anthropic.traced_client import (
    AnthropicTracedClient,
    format_event,
    print_event,
    wrap_anthropic,
)
from avp_anthropic.translate import (
    ModelDriverError,
    ModelResponse,
    ToolOutcome,
    model_response_to_content,
    model_response_usage,
)

__version__ = "0.1.0"

__all__ = [
    "ANTHROPIC_HOSTED_TOOL_KINDS",
    "DEFAULT_PRICES",
    "AnthropicModelDriver",
    "AnthropicTracedClient",
    "Environment",
    "ModelDriverError",
    "ModelResponse",
    "PriceTable",
    "ToolOutcome",
    "__version__",
    "build_anthropic_mcp_servers_from_resolved",
    "build_anthropic_tools",
    "build_descriptor",
    "discover_environment",
    "format_event",
    "model_response_to_content",
    "model_response_usage",
    "print_event",
    "wrap_anthropic",
]
