"""avp.agent_cli — the stock agent command line.

Every AVP agent answers the same three commands, which `avp-conformance` and
the `avp` CLI drive:

- ``ping --out <path>``: write ``{"type": "pong"}`` and exit. Must not boot the
  agent loop (a liveness check), so keep heavy imports inside ``run`` /
  ``describe``.
- ``describe [--out <path>]``: print the agent's ``AgentDescriptor`` JSON (to
  ``--out``, or stdout).
- ``run --commission <json|path> [--built-in <json|path>] --out <path>``: run
  the Commission and write the trajectory to ``--out`` as NDJSON.

An adapter supplies two functions and gets the whole contract::

    from avp.agent_cli import main

    async def run(commission: Commission, sink: EventSink) -> None: ...
    def describe() -> AgentDescriptor: ...   # or async

    raise SystemExit(main(run=run, describe=describe))

Exit codes. ``run`` returns 0 once the trajectory is closed with
``agent_stopped``, including runs that end in an expected failure: a fail-fast
Commission check, a provider auth or rate-limit error, a refusal. Let an
exception escape ``run`` only for a crash (record ``error_occurred`` and
``agent_stopped`` first); it exits non-zero with the traceback on stderr, which
the harness surfaces.

``--built-in`` is the conformance fixture of the agent's pretend defaults. Its
``system_prompt`` and ``prompt`` seed the Commission when it leaves them unset
(the Commission wins). Tool / MCP / subagent built-ins are not simulated.

Argparse keeps this stdlib-only.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.sink import EventSink, jsonl_sink

RunFn = Callable[[Commission, EventSink], Awaitable[None]]
DescribeFn = Callable[[], AgentDescriptor | Awaitable[AgentDescriptor]]


def read_json_arg(value: str) -> Any:
    """Inline JSON (a leading ``{`` / ``[``) or a path to a JSON file."""
    if value.lstrip().startswith(("{", "[")):
        return json.loads(value)
    return json.loads(Path(value).read_text())


def apply_built_in(commission: Commission, built_in: dict[str, Any]) -> Commission:
    """Seed ``system_prompt`` / ``prompt`` from the fixture where the
    Commission leaves them unset."""
    overrides = {
        field: built_in[field]
        for field in ("system_prompt", "prompt")
        if getattr(commission, field) is None and built_in.get(field) is not None
    }
    return commission.model_copy(update=overrides) if overrides else commission


def main(
    *,
    run: RunFn,
    describe: DescribeFn,
    prog: str | None = None,
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog=prog, description="AVP agent entrypoint.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ping = sub.add_parser("ping", help='Write {"type": "pong"} to --out and exit.')
    p_ping.add_argument("--out", required=True)
    p_describe = sub.add_parser("describe", help="Print the agent's AgentDescriptor JSON.")
    p_describe.add_argument("--out")
    p_run = sub.add_parser("run", help="Run a Commission, writing the trajectory to --out.")
    p_run.add_argument("--commission", required=True)
    p_run.add_argument("--built-in", dest="built_in")
    p_run.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "ping":
        Path(args.out).write_text(json.dumps({"type": "pong"}) + "\n")
        return 0

    if args.cmd == "describe":
        descriptor = describe()
        if inspect.isawaitable(descriptor):
            descriptor = asyncio.run(_await(descriptor))
        text = descriptor.model_dump_json(by_alias=True, exclude_none=True, indent=2)
        if args.out:
            Path(args.out).write_text(text + "\n")
        else:
            print(text)
        return 0

    commission = Commission.model_validate(read_json_arg(args.commission))
    if args.built_in is not None:
        commission = apply_built_in(commission, read_json_arg(args.built_in))
    asyncio.run(run(commission, jsonl_sink(Path(args.out))))
    return 0


async def _await(value: Awaitable[AgentDescriptor]) -> AgentDescriptor:
    return await value
