"""Subprocess entry point — reads AEP config from stdin, runs agent, writes stream to stdout."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from agent_execution_protocol import AepConfig
from claude_agent_sdk import ClaudeAgentOptions

from ._query import query, DEFAULT_MODEL


def run_from_stdin() -> None:
    """Read AEP config JSON from stdin line 1, run the agent, emit AEP stream to stdout.

    Stdin remains open after the first line so the runner can read
    ``hook_verdict`` messages from a supervisor during execution.

    Exit codes:
        0  — run completed (any stop reason)
        1  — bad config (empty stdin or invalid JSON)
    """
    raw = sys.stdin.readline()
    if not raw.strip():
        sys.stderr.write("claude-aep-runner: empty stdin — expected AEP config JSON\n")
        sys.exit(1)

    try:
        import json
        config_dict = json.loads(raw)
    except Exception as e:
        sys.stderr.write(f"claude-aep-runner: invalid AEP config JSON: {e}\n")
        sys.exit(1)

    try:
        config = AepConfig.from_dict(config_dict)
    except ValueError as e:
        sys.stderr.write(f"claude-aep-runner: invalid AEP config: {e}\n")
        sys.exit(1)

    asyncio.run(_run(config))


async def _run(config: AepConfig) -> None:
    sdk_model = _strip_vendor(config.model) if config.model else None
    boundary = config.boundary

    opts = ClaudeAgentOptions(
        model=sdk_model,
        system_prompt=config.system_prompt,
        max_turns=boundary.max_steps if boundary else None,
        permission_mode="acceptEdits",
    )

    async for _ in query(
        prompt=config.prompt or "",
        options=opts,
        run_id=config.run_id,
        model=config.model,
        thread_id=config.thread_id,
        tags=config.tags,
        meta=config.meta,
        aep_hooks=config.hooks,
        hook_stdin=sys.stdin if config.hooks else None,
    ):
        pass  # AEP events emitted as side-effect via emit_*


def _strip_vendor(model: str) -> str:
    """Remove vendor prefix for the SDK (e.g. 'anthropic/claude-sonnet-4-6' → 'claude-sonnet-4-6')."""
    return model.split("/", 1)[-1] if "/" in model else model
