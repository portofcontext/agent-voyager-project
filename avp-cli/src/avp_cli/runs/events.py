"""Follow atomic ATIF document updates without replaying old steps or results."""

from pathlib import Path

from pydantic import ValidationError

from avp.trajectory import avp_metadata, documents, parse_trajectory
from avp_cli import console
from avp_cli.console import err


class Follower:
    def __init__(self, trajectory: Path) -> None:
        self.trajectory = trajectory
        self.seen: set[tuple] = set()
        self.last = ""

    def poll(self) -> None:
        try:
            text = self.trajectory.read_text()
        except FileNotFoundError:
            return
        if text == self.last:
            return
        try:
            trajectory = parse_trajectory(text)
        except (ValidationError, ValueError):
            return
        self.last = text
        if console.verbose:
            err.print_json(data=trajectory.to_json_dict())
            return
        for index, doc in enumerate(documents(trajectory)):
            scope = doc.trajectory_id or str(index)
            for step in doc.steps:
                key = (scope, step.step_id, step.source, avp_metadata(step).get("error_code"))
                if key not in self.seen:
                    self.seen.add(key)
                    if step.source == "agent":
                        usage = step.metrics
                        tokens = (
                            f"{usage.prompt_tokens} in, {usage.completion_tokens} out tokens"
                            if usage
                            else "usage unknown"
                        )
                        err.print(f"{doc.agent.name}: response - {tokens}", highlight=False)
                    elif avp_metadata(step).get("error_code"):
                        err.print(
                            f"{avp_metadata(step)['error_code']}: {step.message}",
                            style="red",
                            highlight=False,
                        )
                for call in step.tool_calls or []:
                    call_key = (*key, "call", call.tool_call_id)
                    if call_key not in self.seen:
                        self.seen.add(call_key)
                        err.print(
                            f"tool call - {call.function_name} ({call.tool_call_id})",
                            highlight=False,
                        )
                for n, result in enumerate(step.observation.results if step.observation else []):
                    result_key = (*key, "result", n)
                    if result.content is not None and result_key not in self.seen:
                        self.seen.add(result_key)
                        failed = " - error" if avp_metadata(result).get("is_error") else ""
                        err.print(
                            f"tool result - {result.source_call_id or 'delegation'}{failed}",
                            highlight=False,
                        )
            if avp_metadata(doc).get("complete") and (scope, "complete") not in self.seen:
                self.seen.add((scope, "complete"))
                err.print(
                    f"{doc.agent.name}: {avp_metadata(doc).get('stop_reason', 'complete')}",
                    highlight=False,
                )

    def finish(self) -> None:
        self.poll()
        if self.trajectory.exists() and not self.last:
            err.print("not a valid ATIF document", style="red", highlight=False)


def elapsed(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"
