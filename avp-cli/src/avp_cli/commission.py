"""Build and inspect commissions — which are raw AVP wire `Commission`s.

A commission in the library *is* a wire `Commission` (see `avp_cli.library`), so
inspecting one is just loading + rendering it. `full_dict` keeps every field
(nulls included) so `avp cm describe` teaches the real, complete wire shape;
`validate_file` checks a hand-written Commission JSON against the spec.

`build_commission` is the inverse: it assembles a fresh wire Commission from a
few values (optionally cloning an existing one as the base), enforcing the two
library conventions (`schema_version` is `"0.1"`, `run_id` is the id) and, when
an agent's Descriptor is supplied, that every `enabled_builtin_*` name actually
exists on that agent — the same check the agent would otherwise fail at startup
with `commission_collision`. Catching it here turns a run-time abort into a
build-time error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from avp.commission import Commission
from avp.descriptor import AgentDescriptor


class BuildError(Exception):
    """A commission can't be built as specified (bad field, or an
    `enabled_builtin_*` name the anchor agent doesn't advertise)."""


# (build_commission kwarg, descriptor attribute, the decl's identity field, label)
_ENABLED_CHECKS = [
    ("enabled_builtin_tools", "tools", "name", "tool"),
    ("enabled_builtin_subagents", "subagents", "name", "subagent"),
    ("enabled_builtin_skills", "skills", "name", "skill"),
    ("enabled_builtin_mcp_servers", "mcp_servers", "id", "MCP server"),
]


def build_commission(
    commission_id: str,
    *,
    base: Commission | None = None,
    model: str | None = None,
    prompt: str | None = None,
    system_prompt: str | None = None,
    enabled_builtin_tools: list[str] | None = None,
    enabled_builtin_subagents: list[str] | None = None,
    enabled_builtin_skills: list[str] | None = None,
    enabled_builtin_mcp_servers: list[str] | None = None,
    tags: list[str] | None = None,
    provider_id: str | None = None,
    provider_base_url: str | None = None,
    credential: str | None = None,
    descriptor: AgentDescriptor | None = None,
) -> Commission:
    """Assemble a wire `Commission` for the library.

    `base` (a cloned commission) supplies the starting values — including the
    bulky fields the CLI doesn't author inline (`output_schema`, `mcp_servers`,
    `skills`); pass it via `--from <id>`. Each remaining argument *overrides* the
    base when not `None`; an empty list is a real value (e.g. `[]` exposes none).
    `schema_version` is forced to `"0.1"` and `run_id` to `commission_id`, the
    two library conventions, regardless of the base.

    When `descriptor` is given, every `enabled_builtin_*` name is checked against
    that agent's advertised surface; an unknown name raises `BuildError` rather
    than letting the run abort with `commission_collision`.
    """
    fields: dict[str, Any] = base.model_dump() if base is not None else {}
    fields["schema_version"] = "0.1"
    fields["run_id"] = commission_id
    overrides = {
        "model": model,
        "prompt": prompt,
        "system_prompt": system_prompt,
        "enabled_builtin_tools": enabled_builtin_tools,
        "enabled_builtin_subagents": enabled_builtin_subagents,
        "enabled_builtin_skills": enabled_builtin_skills,
        "enabled_builtin_mcp_servers": enabled_builtin_mcp_servers,
        "tags": tags,
    }
    fields.update({k: v for k, v in overrides.items() if v is not None})

    # Provider routing: --provider-id selects the storefront; --credential names
    # a vault handle (a SecretRef the supervisor resolves, never the value).
    if provider_id is not None:
        provider: dict[str, Any] = {"id": provider_id}
        if provider_base_url is not None:
            provider["base_url"] = provider_base_url
        if credential is not None:
            provider["credential"] = {"vault": credential}
        fields["provider"] = provider
    elif provider_base_url is not None or credential is not None:
        raise BuildError("--provider-base-url / --credential require --provider-id")

    if descriptor is not None:
        _check_enabled_against(fields, descriptor)
    try:
        return Commission.model_validate(fields)
    except ValidationError as exc:
        raise BuildError(str(exc)) from exc


def _check_enabled_against(fields: dict[str, Any], descriptor: AgentDescriptor) -> None:
    """Raise `BuildError` if any `enabled_builtin_*` names aren't on the agent."""
    for kwarg, attr, id_field, label in _ENABLED_CHECKS:
        requested = fields.get(kwarg)
        if not requested:  # None (expose all) or [] (expose none): nothing to check
            continue
        advertised = [getattr(d, id_field) for d in (getattr(descriptor, attr) or [])]
        unknown = [n for n in requested if n not in advertised]
        if unknown:
            have = ", ".join(advertised) if advertised else "(none)"
            raise BuildError(
                f"{descriptor.agent_name} advertises no {label} "
                f"{', '.join(repr(n) for n in unknown)}. It has: {have}. "
                f"Enabling a name the agent doesn't have aborts the run with "
                f"commission_collision."
            )


def load_commission_file(path: str | Path) -> Commission:
    """Load + validate a Commission JSON file (raises ValidationError if bad)."""
    return Commission.model_validate(json.loads(Path(path).read_text()))


def full_dict(c: Commission) -> dict[str, Any]:
    """The complete wire Commission as JSON-able data, nulls kept (the teaching view)."""
    return c.model_dump(mode="json", by_alias=True)


def validate_file(path: str | Path) -> tuple[bool, str]:
    """Return (ok, message): ok on a valid wire Commission, else the errors."""
    try:
        load_commission_file(path)
    except ValidationError as exc:
        return False, str(exc)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"could not read {path}: {exc}"
    return True, ""
