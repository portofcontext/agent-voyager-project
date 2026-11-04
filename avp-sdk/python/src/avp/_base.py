"""Settings shared by the wire models of all three specs."""

import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    WithJsonSchema,
)

if TYPE_CHECKING:
    from avp.trajectory import Event

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


# RFC 3339's `date-time`: `T` between date and time, seconds required, optional
# fraction, and `Z` or a `+hh:mm` / `-hh:mm` offset. `T` and `Z` may be lowercase.
_RFC3339 = r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"


def _rfc3339(time: object) -> object:
    if isinstance(time, datetime):
        return time
    if not isinstance(time, str) or not re.match(_RFC3339, time):
        raise ValueError("time must be an RFC 3339 timestamp, such as 2026-10-28T14:03:12.481Z")
    return datetime.fromisoformat(time.upper())


Timestamp = Annotated[
    AwareDatetime,
    BeforeValidator(_rfc3339),
    WithJsonSchema({"type": "string", "format": "date-time", "pattern": _RFC3339}),
]
"""An RFC 3339 timestamp, read into a timezone-aware `datetime`."""


EventSink = Callable[["Event"], Awaitable[None]]
"""Takes one Trajectory event at a time: a file, a queue, a network stream."""
