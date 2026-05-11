"""avp.commission — Pydantic types for the AVP Commission Spec.

Scoped re-exports of the Commission surface (`Commission` itself,
managed-asset refs, supervisor preamble). This module mirrors the
[Commission spec](../../../../spec/v0.1/commission.md).

Consumers wanting only the run-config object can:

    from avp.commission import Commission, McpServerRef, SubagentRef

…without dragging in Trajectory / Descriptor / Resolver API types.

Source of truth for the Pydantic classes is still `avp.types`.
"""

from __future__ import annotations

from avp.types import (
    Commission,
    McpServerRef,
    SkillRef,
    SubagentRef,
    SupervisorPreamble,
)

__all__ = [
    "Commission",
    "McpServerRef",
    "SkillRef",
    "SubagentRef",
    "SupervisorPreamble",
]
