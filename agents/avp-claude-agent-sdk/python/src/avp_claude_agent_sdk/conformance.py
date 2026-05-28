"""Conformance entrypoint for avp-claude-agent-sdk.

Exposes the agent CLI contract consumed by `avp-conformance`:

- `ping --out <path>` — write a single `{"type": "pong"}` line and exit.
- `describe [--out <path>]` — print the agent's `AgentDescriptor` JSON (the
  pre-flight capability surface: identity, models, tools, skills, MCP). No
  model turn fires; if the capability probe is unavailable the descriptor
  still validates with identity + default_model only.
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

from avp_conformance import load_built_in, load_commission


def _cmd_ping(args: argparse.Namespace) -> int:
    Path(args.out).write_text(json.dumps({"type": "pong"}) + "\n")
    return 0


def _cmd_describe(args: argparse.Namespace) -> int:
    """Print the agent's AgentDescriptor JSON (pre-flight: no model turn).

    Boots a transient probe session to discover the live tool/skill/MCP surface;
    on any probe failure the descriptor degrades to identity + default_model and
    still validates. Heavy imports stay inside this command so `ping` stays
    loop-free.
    """
    import asyncio

    from claude_agent_sdk.types import ClaudeAgentOptions

    from avp_claude_agent_sdk._client import _probe_describe
    from avp_claude_agent_sdk._translator import translate_agent_descriptor

    options = ClaudeAgentOptions(setting_sources=[], strict_mcp_config=True)
    init_data, status = asyncio.run(_probe_describe(options))
    descriptor = translate_agent_descriptor(options, init_data, status)
    text = descriptor.model_dump_json(by_alias=True, exclude_none=True, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
    else:
        print(text)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Run the Claude Agent SDK against the Commission, streaming to --out.

    Honors the feasible part of the `--built-in` fixture: `system_prompt` and
    `prompt` seed the run as defaults, with the Commission overriding when it
    speaks to the same field. Tool / MCP / subagent built-in injection is not
    simulated (a documented gap, same as goose).
    """
    # Imported here, not at module top, so `ping` stays loop-free.
    from claude_agent_sdk.types import ClaudeAgentOptions

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

    # Isolate the run for determinism: don't inherit the host's settings or
    # filesystem MCP config, so the tool surface is governed only by the
    # Commission (not the operator's ~/.claude). Without this the claude CLI
    # picks up ambient MCP servers, making agent_started non-reproducible.
    options = ClaudeAgentOptions(setting_sources=[], strict_mcp_config=True)

    async def agent_main(client: AVPClaudeSDKClient) -> None:
        # The prompt flows from the Commission via `apply_prompt`; the literal
        # passed here is only a fallback when the Commission omits a prompt.
        await client.query("")
        async for _ in client.receive_response():
            pass

    asyncio.run(run_avp_agent(commission, agent_main, sink=sink, options=options))
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

    p_describe = sub.add_parser("describe", help="Print the agent's AgentDescriptor JSON.")
    p_describe.add_argument("--out", required=False)
    p_describe.set_defaults(func=_cmd_describe)

    p_run = sub.add_parser("run", help="Run the agent against a Commission (currently a stub).")
    p_run.add_argument("--commission", required=True)
    p_run.add_argument("--built-in", dest="built_in", required=False)
    p_run.add_argument("--out", required=True)
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
