"""Reference avp-anthropic agent: a complete agent built on the
`avp-anthropic` SDK adapter.

The Anthropic Messages API is a raw HTTP client (no agent loop, no
built-in tools). This script demonstrates how an agent author wires
the AVP pieces together on top of it:

  1. A `ToolDriver` (`ShellTools` below) supplies the local tool
     catalog (bash / read_file / write_file). Real deployments swap in
     a sandboxed / containerized version.
  2. `AnthropicModelDriver` from `avp-anthropic` translates one turn
     between the AVP `AVPAgent` loop and `messages.create(...)`.
  3. `build_descriptor` from `avp-anthropic` produces the
     `AgentDescriptor` the agent advertises pre-flight (via the
     `describe` subcommand) and on-wire (via `agent_described`).
  4. `AVPAgent` from `avp` owns the loop: reads Commission, calls the
     driver each turn, dispatches tools, emits events.
  5. `http_resolver_from_env()` wires `AVP_RESOLVER_URL` if set so
     managed assets in the Commission can be dereferenced.

Used by examples 01, 05, 06 to demonstrate the supervisor /
subprocess pattern: the example IS the supervisor, this script IS the
agent. The Commission gets piped on stdin; events stream out on
stdout as NDJSON.

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
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from pydantic import BaseModel

from avp.agent import AVPAgent, http_resolver_from_env
from avp.agent.drivers import ToolDriver, ToolOutcome
from avp.commission import Commission
from avp.io import write_event
from avp.trajectory import ZERO_SPAN_ID, new_span_id, new_trace_id
from avp_anthropic import (
    AnthropicModelDriver,
    build_anthropic_tools,
    build_descriptor,
)

__version__ = "0.1.0"


# ── Reference tool catalog ────────────────────────────────────────────────────
#
# A minimal local ToolDriver. Real agents replace this with sandboxing,
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


class ShellTools(ToolDriver):
    """Local ToolDriver that handles bash / read_file / write_file."""

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


def descriptor():
    """Build the AgentDescriptor for this reference agent build."""
    return build_descriptor(
        agent_name="anthropic-reference-agent",
        agent_version=__version__,
        built_in_tools=SHELL_TOOL_SCHEMAS,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────


class StdoutSink:
    """SupervisorDriver implementation: write every emitted event to stdout as
    NDJSON. v0.1 has no inbound supervisor channel, so this is the agent's
    only "speaking-to-the-supervisor" surface."""

    def __init__(self, sink: IO[str]) -> None:
        self._sink = sink

    def observe(self, event: object) -> None:
        if isinstance(event, BaseModel):
            write_event(event, file=self._sink)
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
                "avp.state": {
                    "total_cost_usd": 0.0,
                    "total_tokens": 0,
                    "total_turns": 0,
                },
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

    tools_param: list[dict] = build_anthropic_tools(commission, builtins=list(SHELL_TOOL_SCHEMAS))

    driver = AnthropicModelDriver(
        model=model,
        tools_param=tools_param or None,
        max_tokens=args.max_tokens,
    )

    # When the supervisor stands up a resolver service and sets
    # `AVP_RESOLVER_URL` on the agent's env, this dials it via HTTP/JSON-RPC
    # per `spec/v0.1/resolver.md`. AVPAgent calls `avp.resolve` for each
    # Commission-managed asset at startup; after resolution succeeds, the
    # AVPAgent hands the connection material to the driver via
    # `set_resolved_assets`, which translates managed MCP servers into
    # Anthropic's connector parameter for subsequent turns.
    #
    # No AVP_RESOLVER_URL → resolver is None → Commissions with managed
    # asset lists fail at AVPAgent's `resolver_not_configured` gate.
    resolver = http_resolver_from_env()

    agent = AVPAgent(
        commission=commission,
        model=driver,
        tools=ShellTools(),
        supervisor=StdoutSink(sys.stdout),
        agent_builtin_tools=list(SHELL_TOOL_SCHEMAS),
        resolver=resolver,
        descriptor=descriptor(),
    )
    agent.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
