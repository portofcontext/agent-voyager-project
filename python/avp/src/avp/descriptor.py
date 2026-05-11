"""avp.descriptor — Pydantic types for the AVP Agent Descriptor Spec.

Scoped re-export of `AgentDescriptor` (the agent's self-description
shape). This module mirrors the
[Agent Descriptor spec](../../../../spec/v0.1/agent-descriptor.md).

Consumers wanting only the agent-self-description surface can:

    from avp.descriptor import AgentDescriptor

…without dragging in Trajectory / Commission / Resolver API types.

Source of truth for the Pydantic class is still `avp.types`.

The built-in declaration types (`BuiltinTool`, `BuiltinSubagent`,
`BuiltinSkill`) are intentionally internal to `avp.types` in v0.1
(prefixed `_ToolDecl` etc. there) and not re-exported here — the
Descriptor's public surface is the top-level `AgentDescriptor` model
which carries lists of them; downstream typed access goes through the
Pydantic model attributes (`descriptor.built_in_tools[0].name`).
"""

from __future__ import annotations

from avp.types import AgentDescriptor

__all__ = [
    "AgentDescriptor",
]
