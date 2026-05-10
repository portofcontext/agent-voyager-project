"""Category profiles — bundles of supervisor primitives that compile to Commission fields.

A profile pre-declares the agent's tool surface and a framing system prompt.
Building a Commission becomes: pick a profile, override the prompt + run_id +
model. Real supervisor frameworks will keep their own catalog of profiles
per domain; this module ships a small set that's useful for demos.

The profile→Commission compilation lives in `builder.py` so this module stays
purely declarative — easy to read top-to-bottom.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    """A bundle of Commission-shaped defaults the supervisor wants to apply.

    Compiles to: `enabled_builtin_tools` (the agent built-ins this profile
    allows) plus a system_prompt hint that frames the agent's role.
    `enabled_builtin_tools=None` means "all built-ins enabled"; an empty
    list means "no built-ins"; a list narrows to those names. The
    Commission's allowlist is validated against the agent's manifest at
    startup.
    """

    name: str
    description: str
    enabled_builtin_tools: list[str] | None = None
    system_prompt: str | None = None


# ── Presets ──────────────────────────────────────────────────────────────────

DEV_LOOSE = Profile(
    name="dev-loose",
    description=("Permissive surface for exploratory dev work. All built-ins enabled."),
    enabled_builtin_tools=None,
)


READ_ONLY = Profile(
    name="read-only",
    description=(
        "Read-only inspection profile. Useful for code-review and "
        "explanation tasks where you want the agent to look but not touch."
    ),
    enabled_builtin_tools=["read_file"],
)


PRESETS: dict[str, Profile] = {
    DEV_LOOSE.name: DEV_LOOSE,
    READ_ONLY.name: READ_ONLY,
}


def get_profile(name: str) -> Profile:
    if name not in PRESETS:
        raise KeyError(f"unknown profile {name!r}; choose from {sorted(PRESETS)}")
    return PRESETS[name]
