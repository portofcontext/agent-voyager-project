"""Compile a Profile (+ overrides) into a Config the runner can consume."""

from __future__ import annotations

from typing import Any

from aep import Config
from simple_supervisor.profiles import Profile, get_profile


def build_config(
    *,
    run_id: str,
    prompt: str,
    profile: str | Profile = "dev-loose",
    model: str | None = None,
    system_prompt: str | None = None,
    extra_tools: list[dict[str, Any]] | None = None,
    extra_verifiers: list[dict[str, Any]] | None = None,
    boundary_overrides: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> Config:
    """Compose a Config from a profile plus task-specific overrides.

    The profile contributes the *shape of the environment* (allowed_tools,
    verifier templates, boundary defaults). The caller fills in the *task*
    (prompt, run_id, model). Anything passed through `*_overrides` wins.

    `extra_tools` are RPC tools the supervisor will service via stdin. They
    get appended to allowed_tools automatically so the runner exposes them.
    """
    p = profile if isinstance(profile, Profile) else get_profile(profile)

    boundary = dict(p.boundary)
    if boundary_overrides:
        boundary.update(boundary_overrides)

    verifiers = list(p.verifiers)
    if extra_verifiers:
        verifiers.extend(extra_verifiers)

    allowed = list(p.allowed_tools)
    if extra_tools:
        for t in extra_tools:
            if t["name"] not in allowed:
                allowed.append(t["name"])

    return Config(
        schema_version="0.1",
        run_id=run_id,
        prompt=prompt,
        system_prompt=system_prompt or p.system_prompt,
        model=model,
        tools=extra_tools or None,
        allowed_tools=allowed or None,
        verifiers=verifiers or None,
        boundary=boundary or None,
        tags=tags,
        meta=meta,
    )
