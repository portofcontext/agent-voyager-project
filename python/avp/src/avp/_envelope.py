"""Shared CloudEvents 1.0 / OTel span scaffolding for AVP v0.1.

Private module. Consumers MUST import from the spec-scoped namespaces
(`avp.trajectory`, `avp.commission`, `avp.descriptor`, `avp.resolver`)
which re-export the public bits of this file.

What lives here is the cross-cutting wire scaffolding shared by every
spec module:

- CloudEvents 1.0 envelope (`_CloudEventBase`).
- OTel span identification carried on every event's `data`
  (`_SpanData`).
- Source URI (`SOURCE_AGENT`) used by every event type. The agent is
  the sole producer on the wire (spec §8 conformance #1); supervisor
  attribution lives in `run_requested.data` (`avp.commission` +
  `avp.supervisor.*`), not in the envelope's `source` field.
- Pydantic `model_config` presets (`_STRICT`, `_OPEN`) used by every
  spec model.
- ID / timestamp generators used as Pydantic field defaults
  (`now_iso`, `new_event_id`, `new_trace_id`, `new_span_id`,
  `ZERO_SPAN_ID`).

Nothing spec-specific belongs here. Commission, Descriptor, and
trajectory event types live in their own modules.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Iso8601 = str


def now_iso() -> str:
    """ISO 8601 / RFC 3339 timestamp with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def new_event_id() -> str:
    """CloudEvents 1.0 requires `id` unique within `source`. UUID v4 satisfies that."""
    return str(uuid.uuid4())


def new_trace_id() -> str:
    """OTel trace ID: 16 random bytes, hex-encoded (32 lowercase chars)."""
    return secrets.token_hex(16)


def new_span_id() -> str:
    """OTel span ID: 8 random bytes, hex-encoded (16 lowercase chars)."""
    return secrets.token_hex(8)


# 16 zero hex chars: the OTel "absent parent" sentinel for top-level spans.
ZERO_SPAN_ID = "0" * 16


# Source URI (CloudEvents reverse-DNS). The agent is the sole producer on
# the wire (spec §8 conformance #1); every event carries `avp://agent`.
# Supervisor attribution, when applicable, rides inside
# `run_requested.data` (`avp.commission` + `avp.supervisor.*`).
SOURCE_AGENT = "avp://agent"


# Pydantic model_config presets. `populate_by_name=True` lets parsers accept
# either the alias (wire form: dotted) or the Python attribute name. `by_alias`
# is passed at serialization time to emit the alias form on the wire.
_STRICT = ConfigDict(extra="forbid", populate_by_name=True, ser_json_omit_default=False)
_OPEN = ConfigDict(extra="allow", populate_by_name=True)


class _SpanData(BaseModel):
    """Span identification carried by every AVP event's `data` payload.

    `extra="allow"` lets vendor-namespaced extension attributes (e.g.,
    `vendor.priority`, `vendor.trace_id`) round-trip through the trajectory
    verbatim. Spec-defined attributes are validated; unknown keys pass through.
    """

    model_config = _OPEN
    trace_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    span_id: str = Field(min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")
    parent_span_id: str = Field(min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")
    avp_meta: dict[str, Any] | None = Field(default=None, alias="avp.meta")


class _CloudEventBase(BaseModel):
    """Shared CloudEvents 1.0 envelope fields. Specific events override
    `type` and `source` with Literal constants and define `data: <Type>Data`.

    Per CloudEvents §1: required `specversion`, `id`, `source`, `type`.
    Optional: `subject`, `time`, `datacontenttype`, `dataschema`. AVP uses
    `subject` to carry run_id.
    """

    model_config = _STRICT
    specversion: Literal["1.0"] = "1.0"
    id: str = Field(min_length=1, default_factory=new_event_id)
    time: Iso8601 = Field(default_factory=now_iso)
    subject: str | None = Field(default=None, min_length=1)  # run_id
    datacontenttype: str | None = "application/json"
    dataschema: str | None = None
    avp_correlation_id: str | None = Field(default=None, min_length=1, alias="avp.correlation_id")
