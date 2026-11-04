"""Convert a Trajectory event to a CloudEvent, to forward it to event
infrastructure that routes CloudEvents (https://cloudevents.io, version 1.0).

The CloudEvent's `data` is the whole AVP event, so nothing is lost and a
receiver can read it back with `parse_trajectory_event`.
"""

from typing import Any

from avp._base import AVP_VERSION
from avp.trajectory import Event


def to_cloudevent(event: Event, *, source: str) -> dict[str, Any]:
    """The event as a CloudEvent in its JSON format.

    `source` names whoever forwards the event, such as `"avp-cli"` or
    `"https://example.com/runs"`. `type` is the AVP type prefixed with `avp.`,
    and `subject` is the run's ID.
    """
    return {
        "specversion": "1.0",
        "id": event.id,
        "source": source,
        "type": f"avp.{event.type}",
        "subject": event.run_id,
        "time": event.time.isoformat().replace("+00:00", "Z"),
        "datacontenttype": "application/json",
        "avpversion": AVP_VERSION,
        "data": event.model_dump(mode="json", exclude_none=True),
    }
