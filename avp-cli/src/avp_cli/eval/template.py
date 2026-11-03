"""Placeholders in an eval's Commissions and scorer. See docs/eval.md."""

import json
import re

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
        markers = [f"${ns}" for ns in NAMESPACES if f"${ns}" in value]
        if not markers:
            return {k: render(v, scope, f"{where}.{k}" if where else k) for k, v in value.items()}
        [marker, *_] = markers
        path = value[marker]
        if len(value) > 1 or not isinstance(path, str):
            raise TemplateError(f"{where}: {marker} must be the only key, with a field's path")
        return _lookup(scope, marker[1:], path, where)
    return value


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
