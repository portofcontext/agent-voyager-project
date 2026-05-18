"""avp.agent — Abstract base and concrete flavors of AVP agents.

The wire-facing contract — a single async :meth:`emit` — lives on
:class:`avp.agent.base.AVPAgent`. Concrete flavors are siblings:

- :mod:`avp.agent.sink` — :class:`AVPAgentSink` (BETA): one-way fan-out
  to a sink callable.
- :mod:`avp.agent.managed` — :class:`AVPAgentManaged` (ALPHA):
  bidirectional supervisor channel; transport stubs only in v0.1.

All three classes are re-exported from this package for the common
import path::

    from avp.agent import AVPAgent, AVPAgentSink, AVPAgentManaged
"""

from avp.agent.base import AVPAgent
from avp.agent.managed import AVPAgentManaged
from avp.agent.sink import AVPAgentSink, EventSink, stdio_sink

__all__ = ["AVPAgent", "AVPAgentManaged", "AVPAgentSink", "EventSink", "stdio_sink"]
