"""Compile a Profile (+ overrides) into a Commission the agent can consume."""

from __future__ import annotations

from typing import Any

from avp import Commission
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

    The profile contributes the *shape of the environment* (exposed).
    The caller fills in the *task* (prompt, run_id, model).

    Supervisor-side tools (when wanted) are exposed via Commission.mcp_servers
    — supervisors stand up an MCP server (stdio or HTTP) and declare it.
    The builder doesn't currently expose mcp_servers configuration; pass
    it into a Commission(...) directly, or extend this builder.
    """
    p = profile if isinstance(profile, Profile) else get_profile(profile)

    return Commission(
        schema_version="0.1",
        run_id=run_id,
        prompt=prompt,
        system_prompt=system_prompt or p.system_prompt,
        model=model,
        exposed=list(p.exposed) if p.exposed else ["*"],
        tags=tags,
        meta=meta,
    )
