"""`aep-anthropic` stdio entry point (v0.1 model).

Reads ONE Config JSON from stdin, runs the AEPRunner with AnthropicModelDriver,
streams events to stdout, accepts SupervisorMessage RPC replies on stdin
asynchronously after the Config.

In v0.1, the supervisor channel carries only RPC replies — `tool_exec_resolved`
and `re_observation_resolved`. No hooks, no unsolicited messages.
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
from aep.runner.mock import ScriptedTools  # placeholder; replace with your real ToolDriver
from aep_anthropic.driver import AnthropicModelDriver


class StdinSupervisor(SupervisorDriver):
    """SupervisorDriver that reads RPC replies line-by-line from a file (typically stdin).

    Per SPEC.md §5.1: after the Config is consumed, stdin stays open and carries
    NDJSON SupervisorMessage lines. v0.1: only `tool_exec_resolved` and
    `re_observation_resolved` are valid; anything else is malformed.
    """

    def __init__(self, source: IO[str]) -> None:
        self._source = source
        self._tool: dict[str, object] = {}
        self._reobs: dict[str, object] = {}
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
        from aep import ReObservationResolvedEvent, ToolExecResolvedEvent

        if isinstance(msg, ToolExecResolvedEvent):
            self._tool[msg.request_id] = msg
        elif isinstance(msg, ReObservationResolvedEvent):
            self._reobs[msg.request_id] = msg

    def observe(self, event: object) -> None:
        return  # this supervisor is downstream of stdin only

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

    def get_re_observation_response(self, request_id: str, timeout_ms: int) -> object | None:
        return self._wait_for(self._reobs, request_id, timeout_ms)


def _capture_writer(runner: AEPRunner, out: IO[str]) -> None:
    """Patch the runner's trajectory append to also stream events to stdout."""
    original_append = runner.trajectory.append

    def streaming_append(ev):  # type: ignore[no-untyped-def]
        original_append(ev)
        write_event(ev, file=out)

    runner.trajectory.append = streaming_append  # type: ignore[method-assign]


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
    config = Config.model_validate(json.loads(config_blob))

    model = args.model or config.model or "claude-sonnet-4-6"
    tools_param = None
    if config.tools:
        tools_param = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in config.tools
        ]

    driver = AnthropicModelDriver(
        model=model,
        tools_param=tools_param,
        max_tokens=args.max_tokens,
    )
    supervisor = StdinSupervisor(sys.stdin)

    runner = AEPRunner(
        config=config,
        model=driver,
        tools=ScriptedTools(),
        supervisor=supervisor,
    )
    _capture_writer(runner, sys.stdout)
    runner.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
