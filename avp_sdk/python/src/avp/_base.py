"""Settings shared by the wire models of all three specs."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

AVP_VERSION = "0.1"

AgentName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$")]
"""An agent's `agent_name`, also the key of a Commission's `agents` map."""


# Attributes are snake_case. A wire name that isn't (MCP's `inputSchema`) is an
# alias: accepted on input under either name, and used when serializing.
_CONFIG = ConfigDict(
    use_attribute_docstrings=True,
    validate_by_alias=True,
    validate_by_name=True,
    serialize_by_alias=True,
)


class WireModel(BaseModel):
    """A wire object that rejects fields its spec doesn't define."""

    model_config = ConfigDict(**_CONFIG, extra="forbid")


class OpenWireModel(BaseModel):
    """A wire object that keeps fields defined by another standard, such as MCP."""

    model_config = ConfigDict(**_CONFIG, extra="allow")
