"""Placeholders in an eval's Commissions and scorer. See docs/eval.md."""

import json
import re
from dataclasses import dataclass

from pydantic import JsonValue

NAMESPACES = ("item", "run")
PLACEHOLDER = re.compile(r"\{(item|run)\.([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)\}")


class TemplateError(ValueError):
    """A placeholder that can't be filled, with where it is."""


def render(value: JsonValue, scope: dict[str, JsonValue], where: str = "") -> JsonValue:
    """`value` with its placeholders filled from `scope`, which maps each
    namespace available here to its value. `where` is the value's location,
    for errors."""
    if isinstance(value, str):
        return PLACEHOLDER.sub(lambda m: _text(scope, m[1], m[2], where), value)
    if isinstance(value, list):
        return [render(v, scope, f"{where}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict):
        if marker := _marker(value, where):
            return _lookup(scope, marker[1:], str(value[marker]), where)
        return {k: render(v, scope, _key(where, k)) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class Reference:
    """One placeholder in a value."""

    namespace: str
    path: str
    whole: bool
    """`{"$item": path}` rather than `{item.path}` in a string."""
    where: str


def references(value: JsonValue, where: str = "") -> list[Reference]:
    """Every placeholder in `value`, in order, so they can be checked before
    any run. Raises TemplateError for a malformed `$item` or `$run` object."""
    if isinstance(value, str):
        return [Reference(m[1], m[2], False, where) for m in PLACEHOLDER.finditer(value)]
    if isinstance(value, list):
        return [r for i, v in enumerate(value) for r in references(v, f"{where}[{i}]")]
    if isinstance(value, dict):
        if marker := _marker(value, where):
            return [Reference(marker[1:], str(value[marker]), True, where)]
        return [r for k, v in value.items() for r in references(v, _key(where, k))]
    return []


def check(reference: Reference, scope: dict[str, JsonValue]) -> None:
    """Raises TemplateError when `reference` can't be filled from `scope`."""
    if reference.whole:
        _lookup(scope, reference.namespace, reference.path, reference.where)
    else:
        _text(scope, reference.namespace, reference.path, reference.where)


def _key(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


def _marker(value: dict[str, JsonValue], where: str) -> str | None:
    """`$item` or `$run` when `value` is a whole-value placeholder."""
    markers = [f"${ns}" for ns in NAMESPACES if f"${ns}" in value]
    if not markers:
        return None
    [marker, *_] = markers
    if len(value) > 1 or not isinstance(value[marker], str):
        raise TemplateError(f"{where}: {marker} must be the only key, with a field's path")
    return marker


def _lookup(scope: dict[str, JsonValue], namespace: str, path: str, where: str) -> JsonValue:
    if namespace not in scope:
        raise TemplateError(f"{where}: {namespace} isn't available here")
    value = scope[namespace]
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise TemplateError(f"{where}: {namespace} has no field {path!r}")
        value = value[key]
    return value


def _text(scope: dict[str, JsonValue], namespace: str, path: str, where: str) -> str:
    value = _lookup(scope, namespace, path, where)
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return json.dumps(value)
    raise TemplateError(
        f"{where}: {namespace}.{path} isn't text; insert it whole with "
        f'{{"${namespace}": "{path}"}}'
    )
