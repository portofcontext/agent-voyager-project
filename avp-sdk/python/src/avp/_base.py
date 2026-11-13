"""Settings shared by the wire models of the AVP specs."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
)

if TYPE_CHECKING:
    from avp.trajectory import Recording

AVP_VERSION = "0.1"

AgentName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$")]
"""An agent's `agent_name`, also the key of a Commission's `agents` map."""


def _object_schema(schema: dict[str, JsonValue]) -> dict[str, JsonValue]:
    if schema.get("type") != "object":
        raise ValueError('MCP requires the schema\'s "type" to be "object"')
    return schema


ObjectSchema = Annotated[
    dict[str, JsonValue],
    AfterValidator(_object_schema),
    Field(json_schema_extra={"properties": {"type": {"const": "object"}}, "required": ["type"]}),
]
"""A JSON Schema whose `type` is `"object"`, as MCP requires of a tool's schemas
and a Commission requires of its `output_schema`."""


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


TrajectorySink = Callable[["Recording"], Awaitable[None]]
"""Receives the current ATIF document and assets after each Recorder update."""
