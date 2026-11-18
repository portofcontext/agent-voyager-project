"""What `avp run` prints from a finished run's Trajectory."""

from pathlib import Path

from pydantic import ValidationError

from avp.trajectory import avp_metadata, documents, parse_trajectory
from avp_cli import console
from avp_cli.console import err


def show(path: Path) -> None:
    """Print each model response, tool call, tool result, and error in the
    Trajectory at `path`, and how each trajectory stopped. With --verbose, the
    whole document. Nothing when the agent wrote no Trajectory."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        return
    try:
        trajectory = parse_trajectory(text)
    except (ValidationError, ValueError):
        err.print("not a valid ATIF document", style="red", highlight=False)
        return
    if console.verbose:
        err.print_json(data=trajectory.to_json_dict())
        return
    for doc in documents(trajectory):
        for step in doc.steps:
            code = avp_metadata(step).get("error_code")
            if step.source == "agent":
                usage = step.metrics
                tokens = (
                    f"{usage.prompt_tokens} in, {usage.completion_tokens} out tokens"
                    if usage
                    else "usage unknown"
                )
                err.print(f"{doc.agent.name}: response - {tokens}", highlight=False)
            elif code:
                err.print(f"{code}: {step.message}", style="red", highlight=False)
            for call in step.tool_calls or []:
                err.print(
                    f"tool call - {call.function_name} ({call.tool_call_id})", highlight=False
                )
            for result in step.observation.results if step.observation else []:
                failed = " - error" if avp_metadata(result).get("is_error") else ""
                err.print(
                    f"tool result - {result.source_call_id or 'delegation'}{failed}",
                    highlight=False,
                )
        if reason := avp_metadata(doc).get("stop_reason"):
            err.print(f"{doc.agent.name}: {reason}", highlight=False)


def elapsed(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"
