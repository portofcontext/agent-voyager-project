"""Build and inspect commissions — which are raw AVP wire `Commission`s.

A commission in the library *is* a wire `Commission` (see `avp_cli.library`), so
inspecting one is just loading + rendering it. `full_dict` keeps every field
(nulls included) so `avp cm describe` teaches the real, complete wire shape;
`validate_file` checks a hand-written Commission JSON against the spec.

`build_commission` is the inverse: it generates a complete wire Commission
(optionally cloning an existing one as the base), enforcing the two library
conventions (`schema_version` is `"0.1"`, `run_id` is the id). Generation is
descriptor-driven and total: given an agent's Descriptor it enumerates the
agent's FULL builtin surface into the per-agent `enabled_builtin_*` maps and
pins `agent_versions`, so the file on disk is explicit and ready to edit
(delete lines to restrict) rather than assembled through a wizard. It also
validates the agent's own allowlist entries against the Descriptor — the same
check the agent would otherwise fail at startup with `commission_collision`.
Catching it here turns a run-time abort into a build-time error.
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


# (Commission field, descriptor attribute, the decl's identity field, label)
_ENABLED_CHECKS = [
    ("enabled_builtin_tools", "tools", "name", "tool"),
    ("enabled_builtin_subagents", "subagents", "name", "subagent"),
    ("enabled_builtin_skills", "skills", "name", "skill"),
    ("enabled_builtin_mcp_servers", "mcp_servers", "id", "MCP server"),
]

# The generated sample prompt: instructive, eval-ready ({input} is the slot the
# eval engine fills per dataset case), and obviously meant to be rewritten.
SAMPLE_PROMPT = (
    "You are being evaluated. Complete the task below, then output ONLY the "
    "final answer (no preamble).\n\n{input}"
)

# Known-good cheap slug for generated files when the agent declares no usable
# default; the file is meant to be edited, and a wrong-but-valid sample beats
# a crash on a blank field.
SAMPLE_MODEL = "anthropic/claude-haiku-4-5-20251001"


def generated_surface(descriptor: AgentDescriptor) -> dict[str, Any]:
    """The descriptor's FULL builtin surface as explicit per-agent allowlist
    maps, plus the version pin: the generated-commission starting point. Every
    advertised name is enumerated under the agent's own `agent_name` key so
    restricting is deleting lines; categories the agent doesn't advertise are
    omitted (an empty list would mean "expose none", not "default")."""
    name = descriptor.agent_name
    out: dict[str, Any] = {"agent_versions": {name: descriptor.agent_version}}
    for field, attr, id_field, _ in _ENABLED_CHECKS:
        names = [getattr(d, id_field) for d in (getattr(descriptor, attr) or [])]
        if names:
            out[field] = {name: names}
    return out


def build_commission(
    commission_id: str,
    *,
    base: Commission | None = None,
    model: str | None = None,
    tags: list[str] | None = None,
    provider_id: str | None = None,
    provider_base_url: str | None = None,
    credential: str | None = None,
    descriptor: AgentDescriptor | None = None,
) -> Commission:
    """Generate a complete wire `Commission` for the library.

    `base` (a cloned commission, via `--from <id>`) supplies the starting
    values, including the bulky fields the CLI doesn't author inline
    (`output_schema`, `mcp_servers`, `skills`). Without a base, `descriptor`
    drives generation: the agent's full builtin surface lands in the
    per-agent `enabled_builtin_*` maps and `agent_versions` pins the build
    (see `generated_surface`). `schema_version` is forced to `"0.1"` and
    `run_id` to `commission_id`, the two library conventions, regardless.
    `model` falls back to the base's, then the descriptor's `default_model`
    (when it's already a canonical slug), then `SAMPLE_MODEL`; a missing
    prompt gets `SAMPLE_PROMPT`. The result always validates: the generated
    file is a complete, runnable starting point to edit, never a crash.

    When `descriptor` is given, its own allowlist entries are checked against
    its advertised surface; an unknown name raises `BuildError` rather than
    letting the run abort with `commission_collision`.
    """
    fields: dict[str, Any] = base.model_dump() if base is not None else {}
    if base is None and descriptor is not None:
        fields.update(generated_surface(descriptor))
    fields["schema_version"] = "0.1"
    fields["run_id"] = commission_id
    if model is not None:
        fields["model"] = model
    if not fields.get("model"):
        default = descriptor.default_model if descriptor else None
        fields["model"] = default if default and "/" in default else SAMPLE_MODEL
    if not fields.get("prompt"):
        fields["prompt"] = SAMPLE_PROMPT
    if tags is not None:
        fields["tags"] = tags

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
    """Raise `BuildError` if the descriptor's own allowlist entries name things
    the agent doesn't advertise. Each `enabled_builtin_*` field is a per-agent
    map; only the entries under THIS descriptor's `agent_name` are checkable
    here (other agents' keys validate against their own descriptors)."""
    for field, attr, id_field, label in _ENABLED_CHECKS:
        allow_map = fields.get(field)
        if not allow_map:
            continue
        requested = allow_map.get(descriptor.agent_name)
        if not requested:
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
