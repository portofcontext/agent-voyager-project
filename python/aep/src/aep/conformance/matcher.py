"""Partial-match logic shared between case expectations and supervisor scripting.

A `match` is a dict of expected key/values. The pattern matches a target dict iff
every key in the pattern is present in the target with a deep-equal value (object
matchers recurse; arrays must match exactly; scalars use strict equality).
"""

from __future__ import annotations

from typing import Any


def matches_partial(pattern: dict[str, Any], target: dict[str, Any]) -> bool:
    """Return True if every key/value in pattern is present and equal in target."""
    for key, expected in pattern.items():
        if key not in target:
            return False
        actual = target[key]
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                return False
            if not matches_partial(expected, actual):
                return False
        elif isinstance(expected, list):
            if not isinstance(actual, list) or len(actual) != len(expected):
                return False
            for e, a in zip(expected, actual, strict=False):
                if isinstance(e, dict) and isinstance(a, dict):
                    if not matches_partial(e, a):
                        return False
                elif e != a:
                    return False
        else:
            if expected != actual:
                return False
    return True
