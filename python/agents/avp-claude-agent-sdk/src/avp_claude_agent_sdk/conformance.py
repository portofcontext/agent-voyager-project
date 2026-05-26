"""Conformance entrypoint for avp-claude-agent-sdk.

Exposes the agent CLI contract consumed by `avp-conformance`:

- `ping --out <path>` — write a single `{"type": "pong"}` line and exit.
- `run --commission <json|path> [--built-in <json|path>] --out <path>` —
  run the agent against the given Commission and stream AVP trajectory
  events to the output file as NDJSON, one event per line.

See the avp package's `conformance/CHECKLIST.md` for the SDK-author flow.
Argparse is intentional here: this entrypoint stays stdlib-only so it
doesn't pull a CLI framework into the agent package. `ping` must not import
the agent loop (it's a liveness check), so the heavy imports live inside
`_cmd_run`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from avp.conformance import load_built_in, load_commission


def _cmd_ping(args: argparse.Namespace) -> int:
    Path(args.out).write_text(json.dumps({"type": "pong"}) + "\n")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Run the Claude Agent SDK against the Commission, streaming to --out.

    Honors the feasible part of the `--built-in` fixture: `system_prompt` and
    `prompt` seed the run as defaults, with the Commission overriding when it
    speaks to the same field. Tool / MCP / subagent built-in injection is not
    simulated (a documented gap, same as goose).
    """
    # Imported here, not at module top, so `ping` stays loop-free.
    from avp.sink import jsonl_sink
    from avp_claude_agent_sdk import AVPClaudeSDKClient, run_avp_agent

    commission = load_commission(args.commission)
    if args.built_in is not None:
        built_in = load_built_in(args.built_in)
        overrides = {}
        if commission.system_prompt is None and built_in.system_prompt is not None:
            overrides["system_prompt"] = built_in.system_prompt
        if commission.prompt is None and built_in.prompt is not None:
            overrides["prompt"] = built_in.prompt
        if overrides:
            commission = commission.model_copy(update=overrides)

    sink = jsonl_sink(Path(args.out))

    async def agent_main(client: AVPClaudeSDKClient) -> None:
        # The prompt flows from the Commission via `apply_prompt`; the literal
        # passed here is only a fallback when the Commission omits a prompt.
        await client.query("")
        async for _ in client.receive_response():
            pass

    asyncio.run(run_avp_agent(commission, agent_main, sink=sink))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avp-claude-agent-sdk-conformance",
        description="Conformance entrypoint for avp-claude-agent-sdk.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ping = sub.add_parser("ping", help='Write {"type": "pong"} to --out and exit.')
    p_ping.add_argument("--out", required=True)
    p_ping.set_defaults(func=_cmd_ping)

    p_run = sub.add_parser("run", help="Run the agent against a Commission (currently a stub).")
    p_run.add_argument("--commission", required=True)
    p_run.add_argument("--built-in", dest="built_in", required=False)
    p_run.add_argument("--out", required=True)
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
