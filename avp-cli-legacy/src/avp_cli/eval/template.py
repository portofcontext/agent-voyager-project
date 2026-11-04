"""The eval format's ONE template-substitution rule (see EVAL-FORMAT.md §3).

Every templated string in the eval format renders through `render`, with the
same grammar and algorithm, so any implementation (this CLI, the cloud, a
third-party runner) substitutes identically:

  - A variable token is `{name}` where `name` matches `[A-Za-z_][A-Za-z0-9_]*`.
    Nothing else is template syntax: no format specs (`{x:>10}`), no attribute
    or index access (`{a.b}`, `{a[0]}`), no `{{` escapes.
  - Substitution is a single pass over the template; replacement text is never
    rescanned, so a value containing `{input}` stays literal.
  - String values substitute verbatim; non-string values substitute as their
    JSON encoding (`json.dumps`), so booleans render `true`/`false` in every
    implementation rather than a host language's spelling.
  - A token whose name is NOT a defined variable is plain text, left verbatim.
    That keeps prompts brace-safe (`Return JSON {city, country}: {input}`
    renders with the example intact). Per-context strictness decides whether
    such tokens are *allowed*: contexts that map fields (a dataset `input`
    template, the judge template) pass `strict=True` so a typo'd field name
    is a load-time error instead of silently-literal text.

There is deliberately no escape syntax: a template cannot produce a literal
occurrence of a defined variable's own token. Renaming the variable slot is
the documented workaround, and the simplicity is what makes the rule
re-implementable from one paragraph.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

_TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class TemplateError(Exception):
    """A strict-context template references names its variable set lacks."""


def variables_in(template: str) -> list[str]:
    """Every `{name}` token in `template`, in order, duplicates kept."""
    return _TOKEN.findall(template)


def render(template: str, variables: Mapping[str, Any], *, strict: bool = False) -> str:
    """Substitute `variables` into `template` per the eval format's rule.

    `strict=True` (field-mapping contexts) raises `TemplateError` when the
    template carries a token naming no defined variable; `strict=False`
    (prompt contexts) leaves such tokens verbatim.
    """
    if strict:
        unknown = sorted({n for n in variables_in(template) if n not in variables})
        if unknown:
            known = ", ".join(sorted(map(str, variables))) or "(none)"
            raise TemplateError(
                f"template references unknown name(s) {', '.join(unknown)}; available: {known}"
            )

    def _sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in variables:
            return m.group(0)
        value = variables[name]
        return value if isinstance(value, str) else json.dumps(value)

    return _TOKEN.sub(_sub, template)
