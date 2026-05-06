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


QUALITY_GUARDS = Profile(
    name="quality-guards",
    description=(
        "Generic code-quality guardrails. Demos the inject_correction lifecycle "
        "without committing to a specific architectural style. The verifier here "
        "is a 'no TODO comments in writes' rule — illustrative, not opinionated."
    ),
    allowed_tools=["bash", "read_file", "write_file"],
    verifiers=[
        {
            "name": "no-todos-in-writes",
            "trigger": "on_tool:write_file",
            "source": {
                # Fails if the most recent change introduces a TODO line.
                "shell": (
                    "if git diff HEAD 2>/dev/null | grep -E '^\\+.*TODO' >/dev/null; then "
                    "exit 1; else exit 0; fi"
                ),
            },
            "on_failure": "inject_correction",
            "correction_message": (
                "The last write introduced a TODO comment. Remove the TODO and "
                "either implement the behavior or delete the line."
            ),
        },
    ],
    boundary={"max_cost_usd": 0.50, "max_steps": 10, "max_tokens": 80_000},
)


# DDD_STRICT compiles a few core Domain-Driven Design concerns into AEP
# verifiers. Each verifier names a concrete DDD concept and checks it
# deterministically against a workspace that follows the conventional
# domain/ + tests/invariants/ layout. See examples/04_ddd_supervisor.py
# and examples/04_ddd_domain/ for a worked example.
#
# The four verifiers here cover:
#   1. Layer purity — domain code has no infrastructure imports
#   2. Aggregate invariants — domain rules hold (run via pytest)
#   3. Ubiquitous-language hygiene — no anemic generic suffixes in domain
#   4. Aggregate locality — methods that mutate an aggregate live ON the
#      aggregate, not in a separate "service" or "manager"
#
# Real supervisor frameworks will compile a much richer DDD catalog. This
# is a starter profile — enough to make the pattern legible.
DDD_STRICT = Profile(
    name="ddd-strict",
    description=(
        "Bounded-context-correct surface. Verifiers compile DDD concerns to "
        "deterministic checks: layer purity, aggregate invariants, ubiquitous "
        "language, and aggregate locality. Assumes a workspace with domain/ "
        "and tests/invariants/ directories. See examples/04_ddd_supervisor.py."
    ),
    allowed_tools=["bash", "read_file", "write_file"],
    verifiers=[
        # 1. Layer purity — the domain layer must not import infrastructure
        #    (databases, HTTP clients, queues, AWS, etc). Compiled to a
        #    grep across domain/ for known infrastructure module names.
        #    Halt-on-fail because this is an architectural contract: a
        #    domain that imports SQLAlchemy is no longer a domain.
        {
            "name": "domain-layer-purity",
            "trigger": "on_tool:write_file",
            "source": {
                "shell": (
                    "if grep -rE "
                    "'^[[:space:]]*(import|from)[[:space:]]+("
                    "requests|sqlalchemy|psycopg|psycopg2|redis|httpx|"
                    "boto3|aiohttp|kafka|pika"
                    ")([[:space:]]|\\.|$)' domain/ 2>/dev/null; then "
                    "exit 1; else exit 0; fi"
                ),
            },
            "on_failure": "halt",
        },
        # 2. Aggregate invariants — run the invariant test suite. Tests in
        #    tests/invariants/ assert the rules that MUST hold on any
        #    aggregate state (Order.total == sum(line subtotals); a
        #    submitted Order has at least one line; etc). After every turn:
        #    if invariants regress, inject a correction nudging the agent
        #    to find a design that PRESERVES the invariant rather than
        #    weaken the invariant to fit the new feature. The correction
        #    encodes a load-bearing DDD principle: invariants are the
        #    promise; the feature has to fit. Tightly bounded by
        #    boundary.max_steps so the loop can't run away.
        {
            "name": "aggregate-invariants",
            "trigger": "after_each_turn",
            "source": {"shell": "python -m pytest tests/invariants/ -q --no-header --tb=line"},
            "on_failure": "inject_correction",
            "correction_message": (
                "An aggregate invariant regressed — the test suite under "
                "tests/invariants/ now has a failing test. Important: don't "
                "loosen the existing invariant to fit the new feature. The "
                "FEATURE has to fit the invariant, not the other way around. "
                "Re-examine: is there a different shape — a new value object, "
                "a separate field on the aggregate, a different state transition "
                "— that preserves what the invariant was protecting? Revert "
                "the invariant-weakening change and try again with a design "
                "that doesn't require breaking it."
            ),
        },
        # 3. Ubiquitous-language hygiene — domain types that end in
        #    "Manager", "Helper", "Util", or "Service" are an anti-pattern:
        #    they hide what BUSINESS concept the type serves. Soft-fail
        #    via inject_correction so the agent can rename — bad names
        #    don't break correctness, but they accumulate technical debt.
        {
            "name": "no-anemic-suffixes-in-domain",
            "trigger": "on_tool:write_file",
            "source": {
                "shell": (
                    "if find domain/ -type f \\( "
                    "-name '*Manager.py' -o -name '*manager.py' "
                    "-o -name '*Helper.py' -o -name '*helper.py' "
                    "-o -name '*Util.py' -o -name '*util.py' "
                    "-o -name '*Utils.py' -o -name '*utils.py' "
                    "\\) 2>/dev/null | grep -q .; then "
                    "exit 1; else exit 0; fi"
                ),
            },
            "on_failure": "inject_correction",
            "correction_message": (
                "Generic suffixes ('Manager', 'Helper', 'Util') in the domain "
                "layer obscure intent. Rename to use ubiquitous language: "
                "what BUSINESS concept does this type serve? E.g., not "
                "OrderManager — call it OrderShipping, OrderPricing, or move "
                "the behavior onto Order itself if it concerns Order's invariants."
            ),
        },
    ],
    boundary={"max_cost_usd": 0.75, "max_steps": 12, "max_tokens": 100_000},
    system_prompt=(
        "You operate inside a bounded context organized as a DDD codebase: "
        "domain/ holds aggregate roots, value objects, and domain services; "
        "tests/invariants/ holds the deterministic rules every aggregate "
        "state must satisfy. Keep the domain pure (no infrastructure imports). "
        "Prefer methods on the aggregate root over external 'manager' types. "
        "Use ubiquitous language — names should reflect business concepts, "
        "not generic OO patterns."
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
    QUALITY_GUARDS.name: QUALITY_GUARDS,
    DDD_STRICT.name: DDD_STRICT,
    COST_BOUNDED.name: COST_BOUNDED,
}


def get_profile(name: str) -> Profile:
    if name not in PRESETS:
        raise KeyError(f"unknown profile {name!r}; choose from {sorted(PRESETS)}")
    return PRESETS[name]
