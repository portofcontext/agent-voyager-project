"""Subprocess entry point — reads AEP config from stdin, runs agent, writes stream to stdout."""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from agent_execution_protocol import AepConfig, AepTool
from claude_agent_sdk import ClaudeAgentOptions

from ._query import query, DEFAULT_MODEL
from ._hooks import (
    read_tool_exec_result,
    emit_tool_exec_request,
    emit_tool_exec_applied,
)


def _load_skill_content(source: str) -> str | None:
    """Load SKILL.md content from a local path or remote URL.

    Returns the raw markdown string, or None if the source cannot be loaded
    (logs a warning to stderr rather than failing the run).
    """
    import urllib.request
    from pathlib import Path

    if source.startswith("http://") or source.startswith("https://"):
        url = source.rstrip("/") + "/SKILL.md" if not source.endswith(".md") else source
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return resp.read().decode("utf-8")
        except Exception as exc:
            sys.stderr.write(
                f"claude-aep-runner: failed to fetch skill from {url}: {exc}\n"
            )
            return None
    else:
        from pathlib import Path

        path = Path(source)
        skill_md = path / "SKILL.md" if path.is_dir() else path
        try:
            return skill_md.read_text()
        except Exception as exc:
            sys.stderr.write(
                f"claude-aep-runner: failed to read skill from {skill_md}: {exc}\n"
            )
            return None


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

    # Claude Agent SDK has no native skill concept — all skills are loaded as
    # SKILL.md content injected into the system prompt.
    # anthropic:* managed skills are not natively supported here; we skip them
    # with a warning (skill_read is still emitted by query() if skills are passed,
    # but for _run we simply note the limitation).
    extra_context: list[str] = []
    for skill in config.skills:
        if skill.source.startswith("anthropic:"):
            sys.stderr.write(
                f"claude-aep-runner: managed skill '{skill.name}' ({skill.source}) "
                "is not supported by this runner — skipping\n"
            )
        else:
            content = _load_skill_content(skill.source)
            if content:
                extra_context.append(content)

    system_prompt = config.system_prompt
    if extra_context:
        injected = "\n\n---\n\n".join(extra_context)
        system_prompt = f"{system_prompt}\n\n{injected}" if system_prompt else injected

    # Build an in-process MCP server for config-declared supervisor tools.
    # Each handler uses the stdin/stdout channel to ask the supervisor for results.
    hook_stdin = sys.stdin if (config.hooks or config.tools) else None
    mcp_servers: dict = {}
    allowed_tools: list[str] = []

    if config.tools:
        from claude_agent_sdk import tool as sdk_tool, create_sdk_mcp_server

        sdk_tools = []
        for aep_tool in config.tools:
            # Capture aep_tool in closure default arg to avoid late-binding issues.
            def _make_handler(t: AepTool) -> Any:
                async def handler(args: dict[str, Any]) -> dict[str, Any]:
                    call_id = uuid.uuid4().hex[:8]
                    emit_tool_exec_request(
                        run_id=config.run_id,
                        step=0,  # step not tracked here; hooks update step_ref
                        call_id=call_id,
                        tool=t.name,
                        input=args,
                    )
                    output, timed_out = await read_tool_exec_result(
                        call_id, hook_stdin, timeout_ms=30000
                    )
                    emit_tool_exec_applied(
                        run_id=config.run_id,
                        step=0,
                        call_id=call_id,
                        tool=t.name,
                        timed_out=timed_out,
                    )
                    return {"content": [{"type": "text", "text": output}]}

                return handler

            decorated = sdk_tool(
                aep_tool.name, aep_tool.description, aep_tool.input_schema
            )(_make_handler(aep_tool))
            sdk_tools.append(decorated)
            allowed_tools.append(f"mcp__aep_supervisor__{aep_tool.name}")

        mcp_servers["aep_supervisor"] = create_sdk_mcp_server(
            name="aep_supervisor",
            version="1.0.0",
            tools=sdk_tools,
        )

    opts = ClaudeAgentOptions(
        model=sdk_model,
        system_prompt=system_prompt,
        max_turns=boundary.max_steps if boundary else None,
        permission_mode="acceptEdits",
        mcp_servers=mcp_servers or None,
        allowed_tools=allowed_tools or None,
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
        hook_stdin=hook_stdin,
    ):
        pass  # AEP events emitted as side-effect via emit_*


def _strip_vendor(model: str) -> str:
    """Remove vendor prefix for the SDK (e.g. 'anthropic/claude-sonnet-4-6' → 'claude-sonnet-4-6')."""
    return model.split("/", 1)[-1] if "/" in model else model
