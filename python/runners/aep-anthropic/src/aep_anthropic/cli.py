"""`aep-anthropic` stdio entry point (v0.1 model).

Reads ONE Config JSON from stdin, runs the AEPRunner with AnthropicModelDriver,
streams events to stdout, accepts tool_exec_resolved RPC replies on stdin
asynchronously after the Config.

In v0.1, the supervisor channel carries only one message type: tool_exec_resolved.
No hooks, no unsolicited messages.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from typing import IO

from aep import Config, parse_supervisor_message, write_event
from aep.runner import AEPRunner
from aep.runner.drivers import SupervisorDriver
from aep_anthropic.driver import AnthropicModelDriver
from aep_anthropic.shell_tools import SHELL_TOOL_SCHEMAS, ShellTools


class StdinSupervisor(SupervisorDriver):
    """SupervisorDriver that reads RPC replies line-by-line from a file (typically stdin)
    and streams every runner-emitted event to a configurable sink (typically stdout).

    Per SPEC.md §5.1: after the Config is consumed, stdin stays open and carries
    NDJSON SupervisorMessage lines. v0.1: only `tool_exec_resolved` is valid;
    anything else is malformed.

    The observe() side is what makes the trajectory observable to the parent
    supervisor — without it the runner's trajectory stays in-process. We write
    NDJSON, one event per line, flushed after each write so the supervisor sees
    events as they happen.
    """

    def __init__(self, source: IO[str], sink: IO[str] | None = None) -> None:
        self._source = source
        self._sink = sink
        self._tool: dict[str, object] = {}
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._stopped = False
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        for raw in self._source:
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                msg = parse_supervisor_message(payload)
            except Exception as e:
                print(f"aep-anthropic: ignoring malformed supervisor message: {e}", file=sys.stderr)
                continue
            with self._cv:
                self._dispatch(msg)
                self._cv.notify_all()
        with self._cv:
            self._stopped = True
            self._cv.notify_all()

    def _dispatch(self, msg: object) -> None:
        from aep import ToolExecResolvedEvent

        if isinstance(msg, ToolExecResolvedEvent):
            self._tool[msg.request_id] = msg

    def observe(self, event: object) -> None:
        if self._sink is None:
            return
        # SupervisorDriver.observe is called for EVERY runner-emitted event (and
        # for the supervisor RPC replies the runner records into the trajectory).
        # Writing it here is what makes the trajectory observable to the parent
        # process. Per SPEC.md §5.1: NDJSON, one event per line, flushed.
        from pydantic import BaseModel as _BM

        if isinstance(event, _BM):
            write_event(event, file=self._sink)
        else:
            # Custom (non-Pydantic) events: passthrough as JSON dict.
            self._sink.write(json.dumps(event) + "\n")
            self._sink.flush()

    def _wait_for(
        self, table: dict[str, object], request_id: str, timeout_ms: int
    ) -> object | None:
        deadline = time.monotonic() + timeout_ms / 1000.0
        with self._cv:
            while True:
                if request_id in table:
                    return table.pop(request_id)
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._stopped:
                    return None
                self._cv.wait(timeout=min(remaining, 0.1))

    def get_tool_exec_response(self, request_id: str, timeout_ms: int) -> object | None:
        return self._wait_for(self._tool, request_id, timeout_ms)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aep-anthropic",
        description="AEP runner over the Anthropic Messages API. Reads a Config from stdin, streams events to stdout.",
    )
    parser.add_argument("--model", default=None, help="Override Config.model.")
    parser.add_argument(
        "--max-tokens", type=int, default=4096, help="Anthropic max_tokens parameter."
    )
    args = parser.parse_args(argv)

    config_blob = sys.stdin.readline()
    if not config_blob.strip():
        print("aep-anthropic: expected one Config JSON line on stdin", file=sys.stderr)
        return 2
    try:
        config = Config.model_validate(json.loads(config_blob))
    except Exception as e:
        # SPEC.md §14: a runner that receives a Config with an unsupported
        # schema_version (or any other invalid Config) MUST emit error_occurred
        # with code='unknown' and a descriptive message, then emit agent_stopped
        # with reason='error'. We can't construct a fully-valid Config here
        # (that's what failed) so we emit minimal hand-rolled NDJSON that still
        # validates against EventBase: type, source, run_id, ts.
        import contextlib
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        run_id = "unknown"
        with contextlib.suppress(Exception):
            run_id = str(json.loads(config_blob).get("run_id", "unknown"))
        ts = _dt.now(_UTC).isoformat().replace("+00:00", "Z")
        sys.stdout.write(
            json.dumps(
                {
                    "type": "error_occurred",
                    "source": "runner",
                    "run_id": run_id,
                    "ts": ts,
                    "code": "unknown",
                    "message": f"invalid Config: {e}",
                }
            )
            + "\n"
        )
        sys.stdout.write(
            json.dumps(
                {
                    "type": "agent_stopped",
                    "source": "runner",
                    "run_id": run_id,
                    "ts": ts,
                    "reason": "error",
                    "state": {"total_cost_usd": 0.0, "total_tokens": 0, "total_turns": 0},
                }
            )
            + "\n"
        )
        sys.stdout.flush()
        return 2

    model = args.model or config.model or "claude-sonnet-4-6"

    # Build the tools[] surface we expose to the LLM:
    #  1. Runner built-ins (bash / read_file / write_file)
    #  2. Supervisor-declared RPC tools (Config.tools)
    # Then filter by Config.allowed_tools if it's set.
    tools_param: list[dict] = list(SHELL_TOOL_SCHEMAS)
    if config.tools:
        tools_param.extend(
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in config.tools
        )
    if config.allowed_tools is not None:
        allowed = set(config.allowed_tools)
        tools_param = [t for t in tools_param if t["name"] in allowed]

    driver = AnthropicModelDriver(
        model=model,
        tools_param=tools_param or None,
        max_tokens=args.max_tokens,
    )
    supervisor = StdinSupervisor(sys.stdin, sink=sys.stdout)

    runner = AEPRunner(
        config=config,
        model=driver,
        tools=ShellTools(),
        supervisor=supervisor,
    )
    runner.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
