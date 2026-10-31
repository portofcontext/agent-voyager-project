"""The `run` command's work before the agent's own `run`."""

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import JsonValue, ValidationError

from avp._base import EventSink
from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.trajectory import (
    AgentDescribed,
    AgentDescribedEvent,
    ErrorOccurred,
    ErrorOccurredEvent,
    RunRequested,
    RunRequestedEvent,
)
from avp.utils.preflight import check_commission

RunFn = Callable[[Commission, EventSink], Awaitable[None]]
"""The agent's run. When cancelled, it sends `agent_stopped` (`interrupted`) and
re-raises `CancelledError`."""
DescribeFn = Callable[[], AgentDescriptor | Awaitable[AgentDescriptor]]


def read_commission(value: str) -> JsonValue:
    """The Commission as received: parsed JSON, or the text when it isn't JSON."""
    text = value if value.lstrip().startswith("{") else Path(value).read_text()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _envelope(run_id: str) -> dict[str, Any]:
    return {
        "avp_version": "0.1",
        "id": uuid.uuid4().hex,
        "time": datetime.now(UTC),
        "run_id": run_id,
    }


def _run_id(commission: Commission | None, received: JsonValue) -> str:
    """The Commission's `run_id`, else the one in what was received, else a new one."""
    if commission is not None:
        return commission.run_id
    if isinstance(received, dict):
        run_id = received.get("run_id")
        if isinstance(run_id, str):
            return run_id
    return uuid.uuid4().hex


async def get_descriptor(describe: DescribeFn) -> AgentDescriptor:
    descriptor = describe()
    if isinstance(descriptor, AgentDescriptor):
        return descriptor
    return await descriptor


async def run_commission(
    received: JsonValue, sink: EventSink, run: RunFn, describe: DescribeFn
) -> None:
    """Send `run_requested` and `agent_described`, then either refuse the
    Commission (`invalid_commission`) or call the agent's `run`, which sends
    everything from `agent_started` on."""
    try:
        commission: Commission | None = Commission.model_validate(received)
        refusal = None
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'Commission'}: {e['msg']}" for e in error.errors()
        )
        commission, refusal = None, f"the Commission doesn't match the spec: {problems}"
    run_id = _run_id(commission, received)

    descriptor = await get_descriptor(describe)
    await sink(
        RunRequestedEvent(
            **_envelope(run_id), type="run_requested", data=RunRequested(commission=received)
        )
    )
    await sink(
        AgentDescribedEvent(
            **_envelope(run_id), type="agent_described", data=AgentDescribed(descriptor=descriptor)
        )
    )
    if commission is not None:
        refusal = check_commission(commission, descriptor)
    if commission is None or refusal is not None:
        error = ErrorOccurred(error_code="invalid_commission", error_message=refusal or "")
        await sink(ErrorOccurredEvent(**_envelope(run_id), type="error_occurred", data=error))
        return
    await run(commission, sink)
