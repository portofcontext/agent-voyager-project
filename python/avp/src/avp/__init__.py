"""avp — Python reference implementation for the Agent Voyager Project (v0.1 model).

The wire format is built on CloudEvents 1.0, OpenTelemetry GenAI semantic
conventions, OTel spans, JSON-RPC 2.0, MCP, Agent Skills, and JSON Schema.
See FOUNDATIONS.md for the full mapping.

Public API lives in the spec-scoped submodules; this package's top level
exposes only version metadata. Import wire types and helpers directly from
the module that owns them:

    from avp.commission import Commission, McpServerHttp, McpServerStdio, Skill
    from avp.descriptor import AgentDescriptor
    from avp.trajectory import (
        AgentStartedEvent,
        Event,
        parse_event,
        event_to_wire,
    )
    from avp.tracer import AVPTracer, current_tracer
    from avp.io import iter_events, write_event
    from avp.enums import ErrorCode, StopReason
    from avp.pricing import compute_cost, load_default_prices

Doing it this way keeps the spec ↔ module mapping 1:1 and prevents drift
into a single "everything-bag" import surface.
"""

__version__ = "0.1.0"
SCHEMA_VERSION = "0.1"

__all__ = ["SCHEMA_VERSION", "__version__"]
