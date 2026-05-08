"""`avp-anthropic` stdio entry point (v0.1 model).

Reads ONE Commission JSON from stdin, runs the AVPAgent with AnthropicModelDriver,
streams events to stdout. v0.1 has no agent→supervisor RPC channel — stdin
is read once for the Commission and never again. Supervisor-side tool dispatch
(when wanted) goes through MCP via Commission.mcp_servers.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import IO

from pydantic import BaseModel

from avp import Commission, write_event
from avp.agent import AVPAgent
from avp_anthropic.driver import (
    AnthropicModelDriver,
    build_anthropic_mcp_servers,
    build_anthropic_tools,
)
from avp_anthropic.manifest import manifest as build_manifest
from avp_anthropic.shell_tools import SHELL_TOOL_SCHEMAS, ShellTools
from avp_anthropic.subagent import AnthropicSubagentDriver


class StdoutSink:
    """SupervisorDriver implementation: write every emitted event to stdout
    as NDJSON. v0.1 has no inbound supervisor channel, so this is the
    agent's only "speaking-to-the-supervisor" surface."""

    def __init__(self, sink: IO[str]) -> None:
        self._sink = sink

    def observe(self, event: object) -> None:
        if isinstance(event, BaseModel):
            write_event(event, file=self._sink)
        else:
            # Custom (non-Pydantic) events: passthrough as JSON dict.
            self._sink.write(json.dumps(event) + "\n")
            self._sink.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avp-anthropic",
        description=(
            "AVP agent over the Anthropic Messages API. Reads a Commission from stdin, "
            "streams events to stdout."
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
            "Print this agent's manifest as JSON to stdout and exit. The "
            "payload matches the `agent_described` event the agent emits "
            "between `run_requested` and `agent_started` for the same "
            "agent build."
        ),
    )
    args = parser.parse_args(argv)

    if args.subcommand == "describe":
        sys.stdout.write(
            json.dumps(
                build_manifest().model_dump(by_alias=True, exclude_none=True),
                indent=2,
            )
            + "\n"
        )
        return 0

    commission_blob = sys.stdin.readline()
    if not commission_blob.strip():
        print("avp-anthropic: expected one Commission JSON line on stdin", file=sys.stderr)
        return 2
    try:
        config = Commission.model_validate(json.loads(commission_blob))
    except Exception as e:
        # SPEC.md §14: a agent that receives an invalid Commission MUST emit
        # error_occurred + agent_stopped(reason="error"). The Commission didn't
        # validate, so we emit hand-rolled NDJSON envelopes that satisfy the
        # CloudEvents 1.0 envelope shape directly.
        import contextlib
        import uuid as _uuid
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from avp.types import ZERO_SPAN_ID, new_span_id, new_trace_id

        run_id = "unknown"
        with contextlib.suppress(Exception):
            run_id = str(json.loads(commission_blob).get("run_id", "unknown"))
        ts = _dt.now(_UTC).isoformat().replace("+00:00", "Z")
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
                    "avp.error.message": f"invalid Commission: {e}",
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
        return 2

    model = args.model or config.model or "claude-sonnet-4-6"

    # MCP servers declared in Commission flow into Anthropic's API connector.
    # HTTP-only — stdio servers in the Commission are warned about and skipped
    # by the helper. The API runs the MCP loop inside the request and
    # returns mcp_tool_use / mcp_tool_result blocks alongside the model's
    # text output; this v0.1 prototype forwards the connector but does
    # NOT yet emit per-MCP-tool events on the AVP wire (the trajectory
    # shows the model_turn_ended cost rolled up; per-call detail TBD).
    mcp_servers_param: list[dict] = build_anthropic_mcp_servers(config)

    tools_param: list[dict] = build_anthropic_tools(config, builtins=list(SHELL_TOOL_SCHEMAS))

    driver = AnthropicModelDriver(
        model=model,
        tools_param=tools_param or None,
        mcp_servers_param=mcp_servers_param or None,
        max_tokens=args.max_tokens,
    )

    subagent_driver = AnthropicSubagentDriver(default_model=model) if config.subagents else None

    agent = AVPAgent(
        config=config,
        model=driver,
        tools=ShellTools(),
        supervisor=StdoutSink(sys.stdout),
        agent_builtin_tools=list(SHELL_TOOL_SCHEMAS),
        subagent_driver=subagent_driver,
        manifest=build_manifest(),
    )
    agent.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
