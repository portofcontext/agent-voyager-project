"""A run's events as the agent writes them. The run directory is mounted in the
sandbox, so its lines reach the Trajectory on the host as they are written;
avp reads what is new each time it looks."""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from rich.text import Text

from avp.commission import Commission
from avp.trajectory import (
    AgentDescribedEvent,
    AgentStartedEvent,
    AgentStoppedEvent,
    AssistantMessageEvent,
    ErrorOccurredEvent,
    Event,
    RunRequestedEvent,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    ToolUseBlock,
    parse_trajectory_event,
)
from avp_cli import console
from avp_cli.console import err


class Follower:
    """Prints each complete line of the Trajectory once, as `type - details -
    seconds since the event before`, or with --verbose as its type and the
    whole event. A line the agent is still writing waits for its newline."""

    def __init__(self, trajectory: Path) -> None:
        self.trajectory = trajectory
        self.offset = 0
        self.partial = b""
        self.last = datetime.now(UTC)
        """When the event before was written; for the first, when the agent started."""

    def poll(self) -> None:
        try:
            with self.trajectory.open("rb") as file:
                file.seek(self.offset)
                new = file.read()
        except FileNotFoundError:
            return
        self.offset += len(new)
        *lines, self.partial = (self.partial + new).split(b"\n")
        for line in lines:
            self._show(line)

    def finish(self) -> None:
        """Print what is left, including a last line without a newline."""
        self.poll()
        if self.partial.strip():
            self._show(self.partial)
        self.partial = b""

    def _show(self, line: bytes) -> None:
        if not line.strip():
            return
        if console.verbose:
            _show_whole(line)
        try:
            event = parse_trajectory_event(line)
        except ValidationError as error:
            err.print(
                f"not a valid event: {error.errors()[0]['msg']}", style="red", highlight=False
            )
            return
        if event is None:
            return
        since = max((event.time - self.last).total_seconds(), 0)
        self.last = event.time
        if console.verbose:
            return
        parts: list[str | tuple[str, str]] = [
            (event.type, "bold red" if isinstance(event, ErrorOccurredEvent) else "bold")
        ]
        if about := details(event):
            parts += [" - ", about]
        parts += [" - ", (f"{since:.1f}s", "dim")]
        err.print(Text.assemble(*parts))


def _show_whole(line: bytes) -> None:
    """The event's type in bold, then the event, pretty-printed and colored.
    Every event, including those of a type avp doesn't know."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return
    kind = event.get("type") if isinstance(event, dict) else None
    err.print(console.line((str(kind or "event"), "bold")))
    err.print_json(data=event)


def details(event: Event) -> str:
    """What to show of the event, such as a tool call's ID and name."""
    match event:
        case RunRequestedEvent():
            # A Commission that isn't valid stays as the JSON it was.
            commission = event.data.commission
            if not isinstance(commission, Commission):
                return ""
            return f"{commission.model.provider}/{commission.model.id}"
        case AgentDescribedEvent():
            descriptor = event.data.descriptor
            return f"{descriptor.agent_name} {descriptor.agent_version}"
        case AgentStartedEvent():
            data = event.data
            counts = [
                _count(len(data.tools or []), "tool"),
                _count(len(data.mcp_servers or []), "MCP server"),
                _count(len(data.skills or []), "skill"),
                _count(len(data.subagents or []), "subagent"),
            ]
            return ", ".join([f"{data.model.provider}/{data.model.id}", *filter(None, counts)])
        case AssistantMessageEvent():
            usage = event.data.usage
            shown = [f"{usage.input_tokens} in, {usage.output_tokens} out tokens"]
            if usage.cost_usd is not None:
                shown.append(f"${usage.cost_usd:.4f}")
            calls = sum(isinstance(block, ToolUseBlock) for block in event.data.content)
            if calls:
                shown.append(_count(calls, "tool call"))
            return ", ".join(shown)
        case ToolInvokedEvent():
            server = f" on {event.data.mcp_server_id}" if event.data.mcp_server_id else ""
            return f"{event.data.tool_call_id} {event.data.tool_name}{server}"
        case ToolReturnedEvent():
            failed = ", an error" if event.data.tool_result.is_error else ""
            return f"{event.data.tool_call_id} {event.data.tool_name}{failed}"
        case SubagentInvokedEvent():
            return f"{event.data.invocation_id} {event.data.subagent_name}"
        case SubagentReturnedEvent():
            data = event.data
            return f"{data.invocation_id} {data.subagent_name}, {data.subagent_reason}"
        case ErrorOccurredEvent():
            return f"{event.data.error_code}: {event.data.error_message}"
        case AgentStoppedEvent():
            return event.data.reason
    return ""


def elapsed(seconds: float) -> str:
    """Such as `12s` or `3m 05s`."""
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"


def _count(n: int, thing: str) -> str:
    if not n:
        return ""
    return f"{n} {thing}" if n == 1 else f"{n} {thing}s"
