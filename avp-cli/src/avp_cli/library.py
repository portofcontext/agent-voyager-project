"""The portable commission library: `~/.avp/commissions/<id>.json`.

Each file is a **raw AVP wire `Commission`** (`avp.commission.Commission`) and
nothing else: no tool-specific fields, no eval business logic. That keeps a
commission portable — the same file the local CLI runs is the artifact the cloud
consumes, and the wire format is the contract between them. The only conventions
layered on top live in *code*, not in the file:

  - the **id** is the filename (`<id>.json`), not a field in the Commission;
  - a `{input}` placeholder may appear in the wire `prompt` (a plain string); the
    eval engine substitutes the per-case input and assigns a real `run_id` at run
    time (see `avp_cli.eval.setup.Setup.to_commission`).

`Setup` (the engine's internal pairing of an id with its base Commission) ties
those together — but it never touches the on-disk file shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from avp.commission import Commission
from avp_cli import paths


class CommissionError(Exception):
    """A commission file is missing or isn't a valid wire Commission."""


def _dir(commissions_dir: Path | None) -> Path:
    return commissions_dir or paths.commissions_dir()


def path_for(commission_id: str, *, commissions_dir: Path | None = None) -> Path:
    return _dir(commissions_dir) / f"{commission_id}.json"


def exists(commission_id: str, *, commissions_dir: Path | None = None) -> bool:
    return path_for(commission_id, commissions_dir=commissions_dir).is_file()


def load(commission_id: str, *, commissions_dir: Path | None = None) -> Commission:
    """Load one commission (a wire Commission) from the library by id."""
    p = path_for(commission_id, commissions_dir=commissions_dir)
    if not p.is_file():
        raise CommissionError(
            f"no commission {commission_id!r} in {_dir(commissions_dir)} "
            "(run `avp commission list`, or `avp init` to scaffold some)"
        )
    try:
        return Commission.model_validate(json.loads(p.read_text()))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommissionError(f"could not read commission {p}: {exc}") from exc
    except ValidationError as exc:
        raise CommissionError(f"{p} is not a valid wire Commission: {exc}") from exc


def save(
    commission_id: str,
    commission: Commission,
    *,
    overwrite: bool = False,
    commissions_dir: Path | None = None,
) -> Path:
    """Write a wire Commission to the library as `<id>.json`. Returns its path."""
    d = _dir(commissions_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{commission_id}.json"
    if p.exists() and not overwrite:
        raise FileExistsError(p)
    p.write_text(commission.model_dump_json(by_alias=True, exclude_none=True, indent=2) + "\n")
    return p


def delete(commission_id: str, *, commissions_dir: Path | None = None) -> bool:
    """Remove a commission from the library by id. Returns False if it wasn't there."""
    p = path_for(commission_id, commissions_dir=commissions_dir)
    if not p.is_file():
        return False
    p.unlink()
    return True


def list_commissions(*, commissions_dir: Path | None = None) -> list[tuple[str, Commission]]:
    """Every commission in the library as (id, Commission), sorted by id."""
    out: list[tuple[str, Commission]] = []
    for p in sorted(_dir(commissions_dir).glob("*.json")):
        try:
            out.append((p.stem, Commission.model_validate(json.loads(p.read_text()))))
        except (ValidationError, OSError, json.JSONDecodeError):
            continue
    return out
