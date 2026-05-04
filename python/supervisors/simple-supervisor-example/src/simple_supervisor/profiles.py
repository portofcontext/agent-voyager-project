"""Category profiles — bundles of supervisor primitives that compile to Config fields.

A profile pre-declares "what tools the agent can touch", "what rules it must respect",
"what it must not exceed". Building a Config becomes: pick a profile, override the
prompt + run_id + model. Real supervisor frameworks will keep their own catalog of
profiles per domain; this module ships three that are useful for demos.

The profile→Config compilation lives in `builder.py` so this module stays purely
declarative — easy to read top-to-bottom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Profile:
    """A bundle of Config-shaped defaults the supervisor wants to apply.

    Compiles to: allowed_tools (filter), verifiers (rules), boundary (limits),
    plus a system_prompt hint that frames the agent's role inside this profile.
    """

    name: str
    description: str
    allowed_tools: list[str] = field(default_factory=list)
    verifiers: list[dict[str, Any]] = field(default_factory=list)
    boundary: dict[str, Any] = field(default_factory=dict)
    system_prompt: str | None = None


# ── Presets ──────────────────────────────────────────────────────────────────

DEV_LOOSE = Profile(
    name="dev-loose",
    description=(
        "Permissive surface for exploratory dev work. Generous budget; no halt-on-fail "
        "verifiers, just observation. Use this to show 'what would the agent do if I "
        "didn't gate it'."
    ),
    allowed_tools=["bash", "read_file", "write_file"],
    verifiers=[
        {
            "name": "tracks-edits",
            "trigger": "on_tool:write_file",
            "source": {"shell": "true"},  # always-pass: pure observability marker
            "on_failure": "continue",
        },
    ],
    boundary={"max_cost_usd": 1.00, "max_steps": 20, "max_tokens": 100_000},
)


DDD_STRICT = Profile(
    name="ddd-strict",
    description=(
        "Bounded-context-correct surface. Verifiers HALT on broken invariants. "
        "Tight budget. Self-correcting against a few common mistakes."
    ),
    allowed_tools=["bash", "read_file", "write_file"],
    verifiers=[
        {
            "name": "no-todos-in-writes",
            "trigger": "on_tool:write_file",
            "source": {
                # Fails if the most recent staged or working-tree change introduces a TODO.
                # Demo verifier — a real one would run `cargo test` or `scripts/check_invariants.sh`.
                "shell": (
                    "if git diff HEAD 2>/dev/null | grep -E '^\\+.*TODO' >/dev/null; then "
                    "exit 1; else exit 0; fi"
                ),
            },
            "on_failure": "inject_correction",
            "correction_message": (
                "The last write introduced a TODO comment. Bounded contexts compile to "
                "explicit code, not deferred intent. Remove the TODO and implement the "
                "behavior or delete the line."
            ),
        },
        {
            "name": "tests-pass",
            "trigger": "after_each_turn",
            "source": {"shell": "true"},  # placeholder; supervisor swaps in real test cmd
            "on_failure": "halt",
        },
    ],
    boundary={"max_cost_usd": 0.50, "max_steps": 10, "max_tokens": 80_000},
    system_prompt=(
        "You operate inside a bounded context. Every change must keep aggregate "
        "invariants intact. Prefer making behavior explicit over leaving TODOs."
    ),
)


COST_BOUNDED = Profile(
    name="cost-bounded",
    description=(
        "Read-only inspection profile with a tiny budget. Useful for code-review and "
        "explanation tasks where you want strong cost discipline."
    ),
    allowed_tools=["read_file"],
    verifiers=[],
    boundary={"max_cost_usd": 0.05, "max_steps": 3, "max_tokens": 20_000},
)


PRESETS: dict[str, Profile] = {
    DEV_LOOSE.name: DEV_LOOSE,
    DDD_STRICT.name: DDD_STRICT,
    COST_BOUNDED.name: COST_BOUNDED,
}


def get_profile(name: str) -> Profile:
    if name not in PRESETS:
        raise KeyError(f"unknown profile {name!r}; choose from {sorted(PRESETS)}")
    return PRESETS[name]
