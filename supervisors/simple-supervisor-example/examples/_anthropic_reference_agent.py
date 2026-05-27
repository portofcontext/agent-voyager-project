"""Reference avp-anthropic agent: a complete agent built on the
`avp-anthropic` SDK adapter.

The Anthropic Messages API is a raw HTTP client (no agent loop, no
built-in tools). This script demonstrates how an agent author wires
the AVP pieces together on top of it:

  1. A local tool catalog (`ShellTools` below) supplies bash / read_file
     / write_file. Real deployments swap in a sandboxed version.
  2. `AnthropicModelDriver` from `avp-anthropic` translates one turn
     between AVP history and `messages.create(...)`, returning a
     `ModelResponse`.
  3. `build_descriptor` from `avp-anthropic` produces the
     `AgentDescriptor` the agent advertises pre-flight (via the
     `describe` subcommand) and on-wire (via `agent_described`).
  4. `run_agent` below owns the loop: it reads the Commission, calls the
     driver each turn, emits the `avp.trajectory` events directly to a
     sink, dispatches tools, and stops with a reason. There is no shared
     agent base class; the loop is inlined here (the wire-types binding
     ships no `AVPAgent`).

Used by examples 01, 05, 06 to demonstrate the supervisor / subprocess
pattern: the example IS the supervisor, this script IS the agent. The
Commission gets piped on stdin; events stream out on stdout as NDJSON.

Run directly:
    echo '{"schema_version": "0.1", "run_id": "demo", "model": "claude-haiku-4-5-20251001", "prompt": "say hi"}' \\
        | python examples/_anthropic_reference_agent.py

Print the descriptor without running:
    python examples/_anthropic_reference_agent.py describe
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import uuid as _uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from pydantic import BaseModel

from avp.commission import Commission
from avp.content import ToolResultBlock
from avp.descriptor import AgentDescriptor, ToolDecl
from avp.envelope import ZERO_SPAN_ID, new_span_id, new_trace_id
from avp.trajectory import (
    AgentDescribedData,
    AgentDescribedEvent,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    AssistantMessageData,
    AssistantMessageEvent,
    ErrorCode,
    ErrorOccurredData,
    ErrorOccurredEvent,
    RunRequestedData,
    RunRequestedEvent,
    StopReason,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    event_to_wire,
)
from avp_anthropic import (
    AnthropicModelDriver,
    ModelDriverError,
    ToolOutcome,
    build_anthropic_tools,
    build_descriptor,
    model_response_to_content,
    model_response_usage,
)

__version__ = "0.1.0"

_PROVIDER_NAME = "anthropic"
_MAX_TURNS = 50


# ── Reference tool catalog ────────────────────────────────────────────────────
#
# A minimal local tool catalog. Real agents replace this with sandboxing,
# timeouts, path restrictions, line-limit pagination, etc.

SHELL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "bash",
        "description": (
            "Run a shell command in the agent's working directory. Returns combined "
            "stdout+stderr (truncated at 8KB). Non-zero exit codes return the output "
            "with an error indicator."
        ),
        "input_schema": {
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": "Read a file's contents. Returns the file as a string.",
        "input_schema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "description": "Path to read."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a path, overwriting any existing file. Creates parent dirs.",
        "input_schema": {
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {"type": "string", "description": "Path to write."},
                "content": {"type": "string", "description": "Full file contents."},
            },
            "additionalProperties": False,
        },
    },
]

SHELL_TOOL_NAMES: tuple[str, ...] = tuple(schema["name"] for schema in SHELL_TOOL_SCHEMAS)
_LOCAL_NAMES = set(SHELL_TOOL_NAMES)


class ShellTools:
    """Local tool catalog handling bash / read_file / write_file. Plain class
    (no shared base): `is_local` / `invoke` is the contract the loop calls."""

    def __init__(self, *, timeout_s: float = 30.0, max_output_bytes: int = 8192) -> None:
        self.timeout_s = timeout_s
        self.max_output_bytes = max_output_bytes

    def is_local(self, tool: str) -> bool:
        return tool in _LOCAL_NAMES

    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome:
        if tool == "bash":
            return self._run_bash(str(input.get("command", "")))
        if tool == "read_file":
            return self._read_file(str(input.get("path", "")))
        if tool == "write_file":
            return self._write_file(str(input.get("path", "")), str(input.get("content", "")))
        return ToolOutcome(error=f"reference_agent: unknown tool {tool!r}")

    def _run_bash(self, command: str) -> ToolOutcome:
        if not command:
            return ToolOutcome(error="bash: missing 'command' input")
        try:
            result = subprocess.run(
                ["sh", "-c", command],
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return ToolOutcome(error=f"bash: command exceeded {self.timeout_s}s timeout")
        out = (result.stdout or "") + (("\nSTDERR:\n" + result.stderr) if result.stderr else "")
        if len(out) > self.max_output_bytes:
            out = (
                out[: self.max_output_bytes] + f"\n... [truncated at {self.max_output_bytes} bytes]"
            )
        if result.returncode != 0:
            return ToolOutcome(output=f"(exit {result.returncode})\n{out}", duration_ms=1)
        return ToolOutcome(output=out, duration_ms=1)

    def _read_file(self, path: str) -> ToolOutcome:
        if not path:
            return ToolOutcome(error="read_file: missing 'path' input")
        try:
            content = Path(path).read_text()
        except FileNotFoundError:
            return ToolOutcome(error=f"read_file: file not found: {path}")
        except OSError as e:
            return ToolOutcome(error=f"read_file: {e}")
        if len(content) > self.max_output_bytes:
            content = (
                content[: self.max_output_bytes]
                + f"\n... [truncated at {self.max_output_bytes} bytes]"
            )
        return ToolOutcome(output=content, duration_ms=1)

    def _write_file(self, path: str, content: str) -> ToolOutcome:
        if not path:
            return ToolOutcome(error="write_file: missing 'path' input")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        except OSError as e:
            return ToolOutcome(error=f"write_file: {e}")
        return ToolOutcome(output=f"wrote {len(content)} chars to {path}", duration_ms=1)


# ── Descriptor ────────────────────────────────────────────────────────────────


def descriptor() -> AgentDescriptor:
    """Build the AgentDescriptor for this reference agent build."""
    return build_descriptor(
        agent_name="anthropic-reference-agent",
        agent_version=__version__,
        built_in_tools=SHELL_TOOL_SCHEMAS,
    )


# ── Event sink ──────────────────────────────────────────────────────────────


def stdout_sink(event: BaseModel) -> None:
    """Write one AVP event to stdout as NDJSON. v0.1 has no inbound
    supervisor channel, so this is the agent's only surface."""
    sys.stdout.write(json.dumps(event_to_wire(event)) + "\n")
    sys.stdout.flush()


def _tools_param_to_decls(tools_param: list[dict[str, Any]]) -> list[ToolDecl]:
    """Convert the Anthropic tools[] schema the model sees into the
    `agent_started.avp.tools` `ToolDecl` list (so the wire reflects exactly
    the filtered built-in surface)."""
    return [
        ToolDecl(
            name=t["name"],
            description=t.get("description"),
            inputSchema=t.get("input_schema") or t.get("inputSchema"),
        )
        for t in tools_param
    ]


# ── The agent loop ────────────────────────────────────────────────────────────


def run_agent(
    commission: Commission,
    *,
    driver: AnthropicModelDriver,
    tools: ShellTools,
    desc: AgentDescriptor,
    started_tools: list[ToolDecl],
    sink: Callable[[BaseModel], None] = stdout_sink,
    max_turns: int = _MAX_TURNS,
) -> None:
    """Inlined AVP agent loop over `AnthropicModelDriver`.

    Emits the prelude (`run_requested` -> `agent_described` -> `agent_started`),
    then loops: one `assistant_message` per `driver.step(...)`, `tool_invoked` /
    `tool_returned` per dispatched tool, until the model converges (or refuses,
    or a driver error). Appends each assistant turn to history WITH its
    `tool_calls`, and each tool result as a `role:tool` entry, so the next
    `driver.step` re-renders a valid Anthropic message array.
    """
    trace_id = new_trace_id()
    run_id = commission.run_id
    agent_span = new_span_id()
    supervisor = commission.supervisor

    sink(
        RunRequestedEvent(
            subject=run_id,
            data=RunRequestedData(
                trace_id=trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
                supervisor_name=supervisor.name if supervisor else None,
                supervisor_version=supervisor.version if supervisor else None,
                commission=commission,
            ),
        )
    )
    sink(
        AgentDescribedEvent(
            subject=run_id,
            data=AgentDescribedData(
                trace_id=trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
                descriptor=desc,
            ),
        )
    )
    sink(
        AgentStartedEvent(
            subject=run_id,
            data=AgentStartedData(
                trace_id=trace_id,
                span_id=agent_span,
                parent_span_id=ZERO_SPAN_ID,
                provider_name=_PROVIDER_NAME,
                operation_name="invoke_agent",
                request_model=driver.model,
                prompt=commission.prompt,
                system_prompt=commission.system_prompt,
                tools=started_tools,
                thread_id=commission.thread_id,
                tags=commission.tags,
            ),
        )
    )

    def stop(reason: StopReason, output: Any = None) -> None:
        sink(
            AgentStoppedEvent(
                subject=run_id,
                data=AgentStoppedData(
                    trace_id=trace_id,
                    span_id=new_span_id(),
                    parent_span_id=agent_span,
                    reason=reason,
                    output=output,
                ),
            )
        )

    history: list[dict[str, Any]] = []
    if commission.system_prompt:
        history.append({"role": "system", "content": commission.system_prompt})
    history.append({"role": "user", "content": commission.prompt or ""})

    for step in range(1, max_turns + 1):
        try:
            mr = driver.step(history)
        except ModelDriverError as exc:
            sink(_error_event(run_id, trace_id, agent_span, exc.code, str(exc)))
            stop(StopReason.error)
            return
        except Exception as exc:
            # Surface any unexpected driver crash as agent_crash, then stop.
            sink(_error_event(run_id, trace_id, agent_span, ErrorCode.agent_crash, str(exc)))
            stop(StopReason.error)
            return

        turn_span = new_span_id()
        sink(
            AssistantMessageEvent(
                subject=run_id,
                data=AssistantMessageData(
                    trace_id=trace_id,
                    span_id=turn_span,
                    parent_span_id=agent_span,
                    step=step,
                    duration_ms=mr.duration_ms,
                    content=model_response_to_content(mr),
                    usage=model_response_usage(mr),
                    cost_usd=mr.cost_usd,
                    cost_source=mr.cost_source,  # type: ignore[arg-type]
                    provider_name=_PROVIDER_NAME,
                    request_model=driver.model,
                    response_model=mr.response_model,
                    response_finish_reasons=mr.finish_reasons,
                ),
            )
        )

        # Append the assistant turn WITH its tool_calls; the next driver.step
        # re-renders it, and a tool_result without its matching tool_use is
        # rejected by the API.
        history.append(
            {
                "role": "assistant",
                "content": mr.text or "",
                "tool_calls": [
                    {"call_id": tc.call_id, "tool": tc.tool, "input": tc.input}
                    for tc in mr.tool_calls
                ],
            }
        )

        if mr.refusal is not None:
            stop(StopReason.refused)
            return
        if mr.converged or not mr.tool_calls:
            stop(StopReason.converged, output=mr.text)
            return

        for tc in mr.tool_calls:
            tool_span = new_span_id()
            sink(
                ToolInvokedEvent(
                    subject=run_id,
                    data=ToolInvokedData(
                        trace_id=trace_id,
                        span_id=tool_span,
                        parent_span_id=turn_span,
                        step=step,
                        tool_call_id=tc.call_id,
                        tool_name=tc.tool,
                        tool_input=tc.input,
                        tool_dispatch_target="local",
                    ),
                )
            )
            outcome = tools.invoke(tc.tool, tc.input)
            is_error = outcome.error is not None
            text = outcome.error if is_error else (outcome.output or "")
            sink(
                ToolReturnedEvent(
                    subject=run_id,
                    data=ToolReturnedData(
                        trace_id=trace_id,
                        span_id=new_span_id(),
                        parent_span_id=tool_span,
                        step=step,
                        tool_call_id=tc.call_id,
                        tool_name=tc.tool,
                        duration_ms=max(0, outcome.duration_ms),
                        tool_result=ToolResultBlock(
                            tool_use_id=tc.call_id,
                            content=text,
                            structured_content=(
                                outcome.output_json
                                if isinstance(outcome.output_json, dict)
                                else None
                            ),
                            is_error=is_error or None,
                        ),
                    ),
                )
            )
            history.append({"role": "tool", "call_id": tc.call_id, "output": text})

    # Hit the turn cap without converging: stop cleanly so the trajectory still
    # terminates. A production agent would surface this as its own condition.
    stop(StopReason.converged)


def _error_event(
    run_id: str, trace_id: str, agent_span: str, code: ErrorCode, message: str
) -> ErrorOccurredEvent:
    return ErrorOccurredEvent(
        subject=run_id,
        data=ErrorOccurredData(
            trace_id=trace_id,
            span_id=new_span_id(),
            parent_span_id=agent_span,
            error_code=code,
            error_message=message or "error",
        ),
    )


# ── CLI ───────────────────────────────────────────────────────────────────────


class StdoutSink:
    """Back-compat callable sink wrapper: `StdoutSink(f).observe(event)` writes
    NDJSON to `f`. The loop uses the plain `stdout_sink` function; this remains
    for callers that pass a file object."""

    def __init__(self, sink: IO[str]) -> None:
        self._sink = sink

    def observe(self, event: object) -> None:
        if isinstance(event, BaseModel):
            self._sink.write(json.dumps(event_to_wire(event)) + "\n")
        else:
            self._sink.write(json.dumps(event) + "\n")
        self._sink.flush()


def _emit_commission_validation_failure(commission_blob: str, exc: Exception) -> None:
    """commission.md §6 / trajectory.md §8: an agent that receives an invalid
    Commission MUST emit `error_occurred` + `agent_stopped(reason="error")`.
    Since the Commission didn't validate, we hand-roll the two CloudEvents
    envelopes directly to satisfy the wire-shape MUST."""
    run_id = "unknown"
    with contextlib.suppress(Exception):
        run_id = str(json.loads(commission_blob).get("run_id", "unknown"))
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    trace_id = new_trace_id()
    agent_span = new_span_id()

    for envelope in (
        {
            "specversion": "1.0",
            "id": str(_uuid.uuid4()),
            "source": "avp://agent",
            "type": "avp.error_occurred",
            "subject": run_id,
            "time": ts,
            "datacontenttype": "application/json",
            "data": {
                "trace_id": trace_id,
                "span_id": new_span_id(),
                "parent_span_id": agent_span,
                "avp.error.code": "unknown",
                "avp.error.message": f"invalid Commission: {exc}",
            },
        },
        {
            "specversion": "1.0",
            "id": str(_uuid.uuid4()),
            "source": "avp://agent",
            "type": "avp.agent_stopped",
            "subject": run_id,
            "time": ts,
            "datacontenttype": "application/json",
            "data": {
                "trace_id": trace_id,
                "span_id": agent_span,
                "parent_span_id": ZERO_SPAN_ID,
                "avp.reason": "error",
            },
        },
    ):
        sys.stdout.write(json.dumps(envelope) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="anthropic-reference-agent",
        description=(
            "Reference AVP agent built on the avp-anthropic SDK. Reads a Commission "
            "from stdin, streams events to stdout."
        ),
    )
    parser.add_argument("--model", default=None, help="Override Commission.model.")
    parser.add_argument(
        "--max-tokens", type=int, default=4096, help="Anthropic max_tokens parameter."
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser(
        "describe",
        help=(
            "Print this agent's Descriptor as JSON to stdout and exit. The "
            "payload matches the `agent_described` event the agent emits between "
            "`run_requested` and `agent_started` for the same agent build."
        ),
    )
    args = parser.parse_args(argv)

    if args.subcommand == "describe":
        sys.stdout.write(
            json.dumps(
                descriptor().model_dump(by_alias=True, exclude_none=True),
                indent=2,
            )
            + "\n"
        )
        return 0

    commission_blob = sys.stdin.readline()
    if not commission_blob.strip():
        print(
            "anthropic-reference-agent: expected one Commission JSON line on stdin",
            file=sys.stderr,
        )
        return 2
    try:
        commission = Commission.model_validate(json.loads(commission_blob))
    except Exception as exc:
        _emit_commission_validation_failure(commission_blob, exc)
        return 2

    model = args.model or commission.model or "claude-sonnet-4-6"
    tools_param: list[dict[str, Any]] = build_anthropic_tools(
        commission, builtins=list(SHELL_TOOL_SCHEMAS)
    )
    driver = AnthropicModelDriver(
        model=model,
        tools_param=tools_param or None,
        max_tokens=args.max_tokens,
    )
    run_agent(
        commission,
        driver=driver,
        tools=ShellTools(),
        desc=descriptor(),
        started_tools=_tools_param_to_decls(tools_param),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
