#!/usr/bin/env python3
"""Sync the bundled AVP price table from models.dev.

models.dev (https://models.dev/api.json) is the open, community-maintained
catalog of model pricing (the same source Goose uses). This mirrors its entire
cost table into the single canonical `prices.json` (in the Python `avp`
package), keyed by the models.dev id `<provider>/<model>`, so the default table
covers every model models.dev prices without per-model maintenance. There is
one committed copy: the Rust crate embeds this same file via `include_str!`, and
future language bindings vendor it the same way. Runtime stays offline;
production overrides via `compute_cost(prices=...)`.

    python scripts/sync-prices.py            # dry run: print the table
    python scripts/sync-prices.py --write     # write both prices.json copies
    python scripts/sync-prices.py --check     # exit 1 if a write would change models (CI)

Wire `model` strings are normalized to a models.dev key at lookup time inside
`compute_cost` (a slug like `openai/gpt-4o` is used as-is; a bare provider-native
string like `claude-sonnet-4-6` is qualified with its provider to
`anthropic/claude-sonnet-4-6`), so this script does no per-model mapping; it just
mirrors.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import urllib.request
from pathlib import Path

MODELS_DEV_API = "https://models.dev/api.json"

REPO = Path(__file__).resolve().parent.parent
# Single canonical copy (the Python package); the Rust crate embeds this same
# file via include_str!, and future bindings vendor it the same way.
TARGETS = [REPO / "python/avp/src/avp/data/prices.json"]

# Per-million cost fields we carry, in ModelPrice order.
COST_FIELDS = ("input", "output", "cache_read", "cache_write")


def fetch_catalog() -> dict:
    # models.dev returns 403 to the default python-urllib agent, so identify.
    req = urllib.request.Request(MODELS_DEV_API, headers={"User-Agent": "avp-sync-prices/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def build_models(catalog: dict) -> dict:
    """Flatten models.dev into `{ "<provider>/<model>": {input, output, ...} }`,
    keeping every model that carries a price. Omits cost fields the provider
    does not bill (so e.g. OpenAI models have no `cache_write`)."""
    models: dict[str, dict] = {}
    for provider, pdata in catalog.items():
        for model_id, model in pdata.get("models", {}).items():
            cost = model.get("cost") or {}
            if cost.get("input") is None and cost.get("output") is None:
                continue  # free/local or unpriced; nothing to compute from
            entry = {f: round(float(cost[f]), 6) for f in COST_FIELDS if cost.get(f) is not None}
            models[f"{provider}/{model_id}"] = entry
    # Sorted for stable diffs across syncs.
    return dict(sorted(models.items()))


def build_table(catalog: dict) -> dict:
    return {
        "$schema": (
            "Per-1M-token prices in USD, mirrored from models.dev and keyed by "
            "its `<provider>/<model>` id. Fallback table for the `computed` cost "
            "source: AVP prefers an agent that reports its own cost "
            "(`avp.cost.source` = `reported`), and only when it doesn't is cost "
            "`computed` from this table. `compute_cost` normalizes the wire model "
            "(+ provider) to a key here. Callers may also pass their own table to "
            "`compute_cost(prices=...)`."
        ),
        "$source": "https://models.dev/api.json",
        "$snapshot_date": datetime.date.today().isoformat(),
        "$cache_write_convention": (
            "cache_write is models.dev's cache-write rate (Anthropic's 5-minute "
            "rate). Override the table if your traffic is dominantly 1h-cached."
        ),
        "models": build_models(catalog),
    }


def render(table: dict) -> str:
    return json.dumps(table, indent=2) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write both prices.json copies")
    ap.add_argument("--check", action="store_true", help="exit 1 if a write would change models")
    args = ap.parse_args()

    table = build_table(fetch_catalog())
    rendered = render(table)

    if args.check:
        for target in TARGETS:
            current = json.loads(target.read_text()).get("models") if target.exists() else None
            if current != table["models"]:
                print(f"DRIFT: {target} model prices differ from models.dev", file=sys.stderr)
                sys.exit(1)
        print(f"prices.json in sync with models.dev ({len(table['models'])} models)", file=sys.stderr)
        return

    if args.write:
        for target in TARGETS:
            target.write_text(rendered)
            print(f"wrote {target} ({len(table['models'])} models)", file=sys.stderr)
    else:
        print(rendered)
        print(f"(dry run; {len(table['models'])} models; pass --write to update)", file=sys.stderr)


if __name__ == "__main__":
    main()
