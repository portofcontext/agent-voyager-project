"""`run.json` — an immutable, self-contained snapshot of what one eval run used.

The commission library (`~/.avp/commissions/`) is a mutable working set: editing
or re-installing a commission overwrites it in place, so the library alone can't
tell you what a *past* run actually ran. The fully-resolved per-run Commission the
agent receives is written to a temp dir and deleted when the run ends. That left
provenance scattered (mutable library, deleted temp file, ids-only history, and
the body buried in each trajectory's `run_requested`).

This module closes that: every `avp eval run` writes one `run.json` into the run's
output dir, captured **before the matrix runs** (so a crashed run still records its
inputs) and **independent of later library edits**. Given a run dir you can answer
"exactly what ran" from a single file:

  - the verbatim eval config that was executed (dataset + scorer + commission refs),
  - the full wire Commission body for every id used, with its agent binding,
  - the run parameters (agents, model override, item cap, threshold override),
  - the avp-cli version that produced it.

A run dir is the unit of truth (like a git commit); the library is the working tree.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from avp_cli.eval.setup import Setup

MANIFEST_NAME = "run.json"
MANIFEST_VERSION = "1"


def _cli_version() -> str:
    try:
        return version("avp-cli")
    except PackageNotFoundError:
        return "unknown"


def _commissions_snapshot(setups: list[Setup]) -> dict[str, Any]:
    """The exact base wire Commission per id, with its agent binding, frozen now.

    A copy of each setup's commission as it was loaded for this run, so the
    snapshot is unaffected by later edits to the library file of the same id.
    """
    out: dict[str, Any] = {}
    for s in setups:
        out[s.id] = {
            "agent": s.agent,
            "commission": json.loads(
                s.commission.model_dump_json(by_alias=True, exclude_none=True)
            ),
        }
    return out


def write(
    out_dir: str | Path,
    *,
    run_id: str,
    setups: list[Setup],
    eval_config_path: str | Path | None,
    agents: list[str],
    model_override: str | None,
    max_items: int | None,
    threshold_override: float | None = None,
) -> Path:
    """Write `<out_dir>/run.json` and return its path. Overwrites any existing one
    (a re-run into the same dir reflects the latest inputs)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    eval_config: Any = None
    if eval_config_path is not None:
        p = Path(eval_config_path)
        if p.is_file():
            try:
                eval_config = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                eval_config = None
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "cli_version": _cli_version(),
        "eval_config_path": str(eval_config_path) if eval_config_path else None,
        "eval_config": eval_config,
        "run": {
            "agents": list(agents),
            "model_override": model_override,
            "max_items": max_items,
            "threshold_override": threshold_override,
        },
        "commissions": _commissions_snapshot(setups),
    }
    path = out / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def read(out_dir: str | Path) -> dict[str, Any] | None:
    """The run manifest for a run dir, or None if absent/unreadable (older runs)."""
    p = Path(out_dir) / MANIFEST_NAME
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
