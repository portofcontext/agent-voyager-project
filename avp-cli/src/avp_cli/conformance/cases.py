"""The cases. Each covers one rule: it writes a Commission for the agent and
checks the run's Trajectory. A case can raise `Skip` when the agent's
Descriptor says it lacks what the rule needs."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from avp.commission import AgentSettings, Commission, Model
from avp.descriptor import AgentDescriptor
from avp.trajectory import ErrorOccurredEvent, Event

Level = Literal["MUST", "SHOULD"]


class Skip(Exception):
    """The case doesn't apply to the agent. The message says why."""


@dataclass(frozen=True)
class Context:
    """What a case writes its Commission from."""

    descriptor: AgentDescriptor
    model: Model


@dataclass(frozen=True)
class Run:
    """What a case checks: the agent's events and how its command ended."""

    events: list[Event | None]
    """One per line: None for a type avp doesn't know or an invalid event,
    which the runner already reports."""
    types: list[str]
    """Each line's `type`, including types avp doesn't know."""
    exit_code: int | None


@dataclass(frozen=True)
class Case:
    name: str
    rule: str
    level: Level
    about: str
    commission: Callable[[Context], Commission]
    check: Callable[[Run], list[str]]
    """The problems with the run; none means it passed."""


def run_id(case: str) -> str:
    return f"conformance-{case}-{uuid.uuid4().hex[:8]}"


def _refused(run: Run) -> list[str]:
    """Refused before the run started: `run_requested`, `agent_described`,
    then `error_occurred` with `invalid_commission`, and nothing else."""
    expected = ["run_requested", "agent_described", "error_occurred"]
    if run.types != expected:
        return [f"the events are {', '.join(run.types) or 'none'}; expected {', '.join(expected)}"]
    error = run.events[2]
    if isinstance(error, ErrorOccurredEvent) and error.data.error_code != "invalid_commission":
        return [f"error_occurred has the code {error.data.error_code}, not invalid_commission"]
    return []


OTHER_AGENT = "avp-conformance-other"


def _agents_without_entry(context: Context) -> Commission:
    other = OTHER_AGENT
    if context.descriptor.agent_name == other:
        other += "-2"
    return Commission(
        avp_version="0.1",
        run_id=run_id("agents-without-entry"),
        model=context.model,
        prompt="Say hello.",
        agents={other: AgentSettings()},
    )


CASES: list[Case] = [
    Case(
        name="agents-without-entry",
        rule="commission.5.1",
        level="MUST",
        about="`agents` has no entry for the agent, so it refuses the Commission",
        commission=_agents_without_entry,
        check=_refused,
    ),
]
