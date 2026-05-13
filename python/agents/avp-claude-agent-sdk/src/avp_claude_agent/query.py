"""AVP-compliant wrapper around `claude_agent_sdk.query`."""

import re
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from importlib.metadata import version as _pkg_version
from typing import Any

from claude_agent_sdk import Transport
from claude_agent_sdk import query as _sdk_query
from claude_agent_sdk.types import ClaudeAgentOptions, Message, SystemPromptFile, SystemPromptPreset

from avp._envelope import ZERO_SPAN_ID, new_span_id, new_trace_id
from avp.agent import AVPAgentSink, EventSink, stdio_sink
from avp.commission import Commission, SkillRef
from avp.descriptor import AgentDescriptor
from avp.trajectory import (
    AgentDescribedData,
    AgentDescribedEvent,
    AgentStartedData,
    AgentStartedEvent,
    RunRequestedData,
    RunRequestedEvent,
)

_SKILL_ID = re.compile(r"^[a-z0-9_-]+$")
_SKILL_ID_NONCONFORMING = re.compile(r"[^a-z0-9_-]+")


def _skill_id_for(name: str) -> str:
    """Derive a SkillRef.id (matching `^[a-z0-9_-]+$`) from a skill name.

    Returns the name unchanged when it already matches; otherwise lowercases
    and collapses every non-conforming run into a single `-`, then strips
    leading/trailing `-`. Falls back to "skill" for pathological input.
    Callers must de-duplicate ids across the list.
    """
    if _SKILL_ID.fullmatch(name):
        return name
    slug = _SKILL_ID_NONCONFORMING.sub("-", name.lower()).strip("-")
    return slug or "skill"


def _resolve_system_prompt(
    system_prompt: str | SystemPromptPreset | SystemPromptFile | None,
    extras: dict[str, Any],
) -> str | None:
    """Resolve the SDK's `system_prompt` to the literal text the model will see.

    - `str`: used verbatim.
    - `SystemPromptFile`: best-effort read from disk so the trajectory stays
      self-contained without callers retaining the file. On read failure, the
      file ref is stashed under `extras["system_prompt"]` and None is returned.
    - `SystemPromptPreset`: stashed under `extras["system_prompt"]` (preset
      name / `append` aren't the literal prompt the model receives).
    """
    if system_prompt is None:
        return None
    if isinstance(system_prompt, str):
        return system_prompt
    # `SystemPromptPreset` / `SystemPromptFile` are TypedDicts — plain dicts
    # at runtime — discriminated on the `type` field.
    if system_prompt["type"] == "file":
        try:
            with open(system_prompt["path"], encoding="utf-8") as f:
                return f.read()
        except OSError:
            extras["system_prompt"] = dict(system_prompt)
            return None
    extras["system_prompt"] = dict(system_prompt)
    return None


def _project_commission(
    *,
    run_id: str,
    prompt: str | AsyncIterable[dict[str, Any]],
    options: ClaudeAgentOptions,
) -> tuple[Commission, str | None]:
    """Build a Commission-shaped snapshot of the inputs to this query() call.

    Fields that don't map cleanly to Commission (cwd, permission_mode,
    allowed_tools, etc.) ride under `meta.claude_agent_options` so the
    trajectory audit trail still surfaces them. Returns the resolved literal
    system prompt alongside so the caller can reuse it on `agent_started`
    without re-reading the file.
    """
    extras: dict[str, Any] = {}
    if options.cwd is not None:
        extras["cwd"] = str(options.cwd)
    if options.permission_mode is not None:
        extras["permission_mode"] = options.permission_mode
    if options.allowed_tools:
        extras["allowed_tools"] = list(options.allowed_tools)
    if options.disallowed_tools:
        extras["disallowed_tools"] = list(options.disallowed_tools)
    if options.setting_sources is not None:
        extras["setting_sources"] = list(options.setting_sources)
    if options.max_thinking_tokens is not None:
        extras["max_thinking_tokens"] = options.max_thinking_tokens

    system_prompt_text = _resolve_system_prompt(options.system_prompt, extras)

    # `options.skills` is the caller's explicit declaration of which skills
    # this run uses. The verbatim name goes in `ref` (what the CLI's on-disk
    # discovery resolves); `id` is a slug derived from the name (must match
    # `^[a-z0-9_-]+$`). `"all"` → None on the typed slot (can't enumerate up
    # front; defer to CLI discovery) and noted under `meta`.
    skills: list[SkillRef] | None = None
    if isinstance(options.skills, list):
        used_ids: set[str] = set()
        refs: list[SkillRef] = []
        for name in options.skills:
            base = _skill_id_for(name)
            skill_id, n = base, 2
            while skill_id in used_ids:
                skill_id = f"{base}-{n}"
                n += 1
            used_ids.add(skill_id)
            refs.append(SkillRef(id=skill_id, ref=name))
        skills = refs or None
    elif options.skills == "all":
        extras["skills"] = "all"

    commission = Commission(
        schema_version="0.1",
        run_id=run_id,
        prompt=prompt if isinstance(prompt, str) else None,
        system_prompt=system_prompt_text,
        model=options.model,
        # `options.mcp_servers` / `options.agents` are already-resolved
        # connection material and agent-internal definitions; Commission's
        # slots are opaque supervisor refs the agent dereferences via the
        # AVP Resolver API. They surface on agent_started.data.tools[] and
        # mcp_server_connected events instead (not yet wired).
        mcp_servers=None,
        subagents=None,
        skills=skills,
        meta={"claude_agent_options": extras} if extras else None,
    )
    return commission, system_prompt_text


async def query(
    *,
    prompt: str | AsyncIterable[dict[str, Any]],
    options: ClaudeAgentOptions | None = None,
    transport: Transport | None = None,
    sink: EventSink | None = None,
) -> AsyncIterator[Message]:
    """Drop-in wrapper for `claude_agent_sdk.query` that emits an AVP trajectory.

    Same call surface as `claude_agent_sdk.query` plus a `sink` kwarg.
    `sink` defaults to `avp.agent.stdio_sink` (NDJSON to stdout); pass a
    custom :data:`avp.agent.EventSink` to capture events elsewhere.
    """
    if options is None:
        options = ClaudeAgentOptions()

    avp = AVPAgentSink(sink or stdio_sink)

    trace_id = new_trace_id()
    run_id = str(uuid.uuid4())

    # § 2.1 — run prelude: run_requested, agent_described, agent_started.
    # All three are span-tree roots (parent_span_id = ZERO); agent_started's
    # span_id becomes the agent span that subsequent run events nest under.
    commission, system_prompt_text = _project_commission(
        run_id=run_id, prompt=prompt, options=options
    )
    await avp.emit(
        RunRequestedEvent(
            subject=run_id,
            data=RunRequestedData(
                trace_id=trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
                avp_supervisor_name="unknown",
                avp_commission=commission,
            ),
        )
    )

    descriptor = AgentDescriptor(
        agent_name="avp-claude-agent-sdk",
        agent_version=_pkg_version("avp-claude-agent-sdk"),
        avp_spec_version="0.1",
        default_model=options.model,
    )
    await avp.emit(
        AgentDescribedEvent(
            subject=run_id,
            data=AgentDescribedData(
                trace_id=trace_id,
                span_id=new_span_id(),
                parent_span_id=ZERO_SPAN_ID,
                avp_descriptor=descriptor,
            ),
        )
    )

    agent_span_id = new_span_id()
    await avp.emit(
        AgentStartedEvent(
            subject=run_id,
            data=AgentStartedData(
                trace_id=trace_id,
                span_id=agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                gen_ai_provider_name="anthropic",
                gen_ai_operation_name="invoke_agent",
                gen_ai_request_model=options.model,
                prompt=prompt if isinstance(prompt, str) else None,
                system_prompt=system_prompt_text,
            ),
        )
    )

    async for message in _sdk_query(prompt=prompt, options=options, transport=transport):
        yield message
