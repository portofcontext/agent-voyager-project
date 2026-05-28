"""Inspect commissions — which are raw AVP wire `Commission`s.

A commission in the library *is* a wire `Commission` (see `avp_cli.library`), so
inspecting one is just loading + rendering it. `full_dict` keeps every field
(nulls included) so `avp commission show` teaches the real, complete wire shape;
`validate_file` checks a hand-written Commission JSON against the spec.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from avp.commission import Commission


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
