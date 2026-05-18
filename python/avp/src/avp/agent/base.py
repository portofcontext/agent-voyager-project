"""avp.agent.base — Abstract base for AVP-conformant agents.

:class:`AVPAgent` pins the trajectory-output contract: a single async
:meth:`emit` is the only thing a conformant agent must define. The base
supplies no loop, no driver protocols, and emits no events on its own.

Concrete flavors live in sibling modules:

- :mod:`avp.agent.sink` — :class:`AVPAgentSink` (BETA): one-way fan-out
  to a sink callable (stdout writer, file appender, database insert,
  …).
- :mod:`avp.agent.managed` — :class:`AVPAgentManaged` (ALPHA):
  bidirectional channel with a supervisor; transport bindings stubbed
  for v0.1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from avp.trajectory import Event

if TYPE_CHECKING:
    pass


class AVPAgent(ABC):
    """Abstract base for AVP-conformant agents.

    Subclasses implement :meth:`emit` — how trajectory events leave the
    agent. Run lifecycle and driver protocols (if any) belong to the
    concrete flavor, not the base.
    """

    @abstractmethod
    async def emit(self, event: Event) -> None:
        """Emit one trajectory event via the agent's configured channel."""
