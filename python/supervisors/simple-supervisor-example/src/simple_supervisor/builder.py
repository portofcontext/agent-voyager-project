"""Compile a Profile (+ overrides) into a Commission the agent can consume."""

from __future__ import annotations

from typing import Any

from avp.commission import Commission
from simple_supervisor.profiles import Profile, get_profile


def build_commission(
    *,
    run_id: str,
    prompt: str,
    profile: str | Profile = "dev-loose",
    model: str | None = None,
    system_prompt: str | None = None,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> Commission:
    """Compose a Commission from a profile plus task-specific overrides.

    The profile contributes the *shape of the environment*
    (`enabled_builtin_tools`). The caller fills in the *task*
    (prompt, run_id, model).

    Supervisor-managed assets (`mcp_servers`, `skills`, `subagents` refs)
    are not configured by this builder; pass them into Commission(...)
    directly, or extend this builder.
    """
    p = profile if isinstance(profile, Profile) else get_profile(profile)

    kwargs: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": run_id,
        "prompt": prompt,
        "system_prompt": system_prompt or p.system_prompt,
        "model": model,
        "tags": tags,
        "meta": meta,
    }
    if p.enabled_builtin_tools is not None:
        kwargs["enabled_builtin_tools"] = list(p.enabled_builtin_tools)
    return Commission(**kwargs)
