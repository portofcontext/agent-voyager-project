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
        sys.stderr.write(
            "anthropic-aep-runner: empty stdin — expected AEP config JSON\n"
        )
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

    # Translate AepSkill entries to SDK-native formats.
    # anthropic:<skill_id>@<version> → Anthropic beta API managed skills
    # All other sources → load SKILL.md content and prepend to system prompt
    managed_skills: list[dict] = []
    extra_context: list[str] = []

    for skill in config.skills:
        if skill.source.startswith("anthropic:"):
            # Parse "anthropic:pptx@latest" → skill_id="pptx", version="latest"
            ref = skill.source[len("anthropic:") :]
            skill_id, _, version = ref.partition("@")
            managed_skills.append(
                {
                    "type": "anthropic",
                    "skill_id": skill_id,
                    "version": version or "latest",
                }
            )
        else:
            # Local or remote SKILL.md — load and inject into context
            content = _load_skill_content(skill.source)
            if content:
                extra_context.append(content)

    system_prompt = config.system_prompt
    if extra_context:
        injected = "\n\n---\n\n".join(extra_context)
        system_prompt = f"{system_prompt}\n\n{injected}" if system_prompt else injected

    # Translate AepTool entries to Anthropic API tool format.
    # All config-declared tools are supervisor-executed; the runner presents the
    # schema to the LLM and uses the stdin channel to get results from the supervisor.
    api_tools: list[dict] = []
    supervisor_tool_names: set[str] = set()
    for aep_tool in config.tools:
        api_tools.append(
            {
                "name": aep_tool.name,
                "description": aep_tool.description,
                "input_schema": aep_tool.input_schema,
            }
        )
        supervisor_tool_names.add(aep_tool.name)

    async for _ in query(
        prompt=config.prompt or "",
        model=model,
        tools=api_tools or None,
        supervisor_tools=supervisor_tool_names or None,
        hook_stdin=sys.stdin if supervisor_tool_names else None,
        skills=managed_skills or None,
        system_prompt=system_prompt,
        run_id=config.run_id,
        max_steps=boundary.max_steps if boundary and boundary.max_steps else 20,
        thread_id=config.thread_id,
        tags=config.tags,
        meta=config.meta,
    ):
        pass  # AEP events emitted as side-effect via emit_*


def _load_skill_content(source: str) -> str | None:
    """Load SKILL.md content from a local path or remote URL.

    Returns the raw markdown string, or None if the source cannot be loaded
    (logs a warning to stderr rather than failing the run).
    """
    import urllib.request
    from pathlib import Path

    if source.startswith("http://") or source.startswith("https://"):
        # Remote URL — try to fetch SKILL.md
        url = source.rstrip("/") + "/SKILL.md" if not source.endswith(".md") else source
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return resp.read().decode("utf-8")
        except Exception as exc:
            sys.stderr.write(
                f"anthropic-aep-runner: failed to fetch skill from {url}: {exc}\n"
            )
            return None
    else:
        # Local path
        path = Path(source)
        skill_md = path / "SKILL.md" if path.is_dir() else path
        try:
            return skill_md.read_text()
        except Exception as exc:
            sys.stderr.write(
                f"anthropic-aep-runner: failed to read skill from {skill_md}: {exc}\n"
            )
            return None


def _strip_vendor(model: str) -> str:
    """Remove vendor prefix (e.g. 'anthropic/claude-sonnet-4-6' → 'claude-sonnet-4-6')."""
    return model.split("/", 1)[-1] if "/" in model else model
