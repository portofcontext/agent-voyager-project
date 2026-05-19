"""avp.agent.managed — ALPHA managed-mode agent.

:class:`AVPAgentManaged` is the integrator seam for the bidirectional
supervisor↔agent channel: the supervisor pushes commissions in, the
agent emits trajectory events back out the same transport.

Stubs for v0.1: :meth:`emit`, :meth:`run`, :meth:`serve_stdio`, and
:meth:`serve_ws` all raise :class:`NotImplementedError`. The transport
binding (stdio framing, websocket handshake) lands in a later cut.
"""

from avp.agent.base import AVPAgent
from avp.commission import Commission
from avp.trajectory import Event


class AVPAgentManaged(AVPAgent):
    """ALPHA: managed-mode agent. Bidirectional with a supervisor.

    Stubs for v0.1: :meth:`emit`, :meth:`serve_stdio`, and
    :meth:`serve_ws` raise :class:`NotImplementedError`. The class
    exists so integrators can subclass and implement :meth:`run` today;
    the transport binding lands in a later cut.
    """

    async def emit(self, event: Event) -> None:
        raise NotImplementedError(
            "AVPAgent (managed mode) is ALPHA in v0.1; emit is not yet wired."
        )

    async def run(self, commission: Commission) -> None:
        """Execute the commission. Integrators implement this."""
        raise NotImplementedError("run is an ALPHA stub for v0.1.")

    async def serve_stdio(self) -> None:
        """STUB: bind this agent to a stdio transport (accept commissions
        on stdin, emit trajectory events on stdout)."""
        raise NotImplementedError("serve_stdio is an ALPHA stub for v0.1.")

    async def serve_ws(self) -> None:
        """STUB: bind this agent to a websocket transport (dial supervisor,
        accept commissions, push trajectory events back)."""
        raise NotImplementedError("serve_ws is an ALPHA stub for v0.1.")
