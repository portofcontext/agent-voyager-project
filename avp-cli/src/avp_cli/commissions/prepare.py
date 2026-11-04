"""The supervisor fills identity immediately before sending a Commission."""

from importlib.metadata import version
from uuid import uuid4

from pydantic import JsonValue

from avp.commission import Commission


def prepare(value: dict[str, JsonValue], run_id: str | None = None) -> Commission:
    return Commission.model_validate(
        {
            **value,
            "run_id": run_id if run_id is not None else str(uuid4()),
            "supervisor": {"name": "avp-cli", "version": version("avp-cli")},
        }
    )
