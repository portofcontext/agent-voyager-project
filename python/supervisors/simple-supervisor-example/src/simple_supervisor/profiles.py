"""Category profiles — bundles of supervisor primitives that compile to Commission fields.

A profile pre-declares the agent's tool surface and a framing system prompt.
Building a Commission becomes: pick a profile, override the prompt + run_id +
model. Real supervisor frameworks will keep their own catalog of profiles
per domain; this module ships a small set that's useful for demos.

The profile→Commission compilation lives in `builder.py` so this module stays
purely declarative — easy to read top-to-bottom.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    """A bundle of Commission-shaped defaults the supervisor wants to apply.

    Compiles to: `exposed` (the model-facing name surface, with fnmatch
    glob support) plus a system_prompt hint that frames the agent's role
    inside this profile.
    """

    name: str
    description: str
    exposed: list[str] = field(default_factory=list)
    system_prompt: str | None = None


# ── Presets ──────────────────────────────────────────────────────────────────

DEV_LOOSE = Profile(
    name="dev-loose",
    description=(
        "Permissive surface for exploratory dev work. Use this to show "
        "'what would the agent do if I didn't gate it'."
    ),
    exposed=["bash", "read_file", "write_file"],
)


READ_ONLY = Profile(
    name="read-only",
    description=(
        "Read-only inspection profile. Useful for code-review and "
        "explanation tasks where you want the agent to look but not touch."
    ),
    exposed=["read_file"],
)


PRESETS: dict[str, Profile] = {
    DEV_LOOSE.name: DEV_LOOSE,
    READ_ONLY.name: READ_ONLY,
}


def get_profile(name: str) -> Profile:
    if name not in PRESETS:
        raise KeyError(f"unknown profile {name!r}; choose from {sorted(PRESETS)}")
    return PRESETS[name]
