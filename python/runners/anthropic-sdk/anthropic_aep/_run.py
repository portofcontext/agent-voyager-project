"""Subprocess entry point — reads AEP config from stdin, runs agent, writes stream to stdout."""

from __future__ import annotations

import asyncio
import json
import sys

from agent_execution_protocol import AepConfig

from ._query import query, DEFAULT_MODEL


def run_from_stdin() -> None:
    """Read AEP config JSON from stdin line 1, run the agent, emit AEP stream to stdout.

    This entry point supports text-only conversations (no custom tool handlers,
    since tool implementations are Python code and cannot be serialized). For
    agents that need tools, use library mode instead.

    Exit codes:
        0  — run completed (any stop reason)
        1  — bad config (empty stdin or invalid JSON)
    """
    raw = sys.stdin.readline()
    if not raw.strip():
        sys.stderr.write("anthropic-aep-runner: empty stdin — expected AEP config JSON\n")
        sys.exit(1)

    try:
        config_dict = json.loads(raw)
    except Exception as exc:
        sys.stderr.write(f"anthropic-aep-runner: invalid AEP config JSON: {exc}\n")
        sys.exit(1)

    try:
        config = AepConfig.from_dict(config_dict)
    except ValueError as exc:
        sys.stderr.write(f"anthropic-aep-runner: invalid AEP config: {exc}\n")
        sys.exit(1)

    asyncio.run(_run(config))


async def _run(config: AepConfig) -> None:
    model = _strip_vendor(config.model) if config.model else DEFAULT_MODEL
    boundary = config.boundary

    async for _ in query(
        prompt=config.prompt or "",
        model=model,
        system_prompt=config.system_prompt,
        run_id=config.run_id,
        max_steps=boundary.max_steps if boundary and boundary.max_steps else 20,
        thread_id=config.thread_id,
        tags=config.tags,
        meta=config.meta,
    ):
        pass  # AEP events emitted as side-effect via emit_*


def _strip_vendor(model: str) -> str:
    """Remove vendor prefix (e.g. 'anthropic/claude-sonnet-4-6' → 'claude-sonnet-4-6')."""
    return model.split("/", 1)[-1] if "/" in model else model
