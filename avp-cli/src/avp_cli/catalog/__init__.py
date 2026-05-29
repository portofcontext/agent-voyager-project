"""The `avp init` catalog: real, scaffold-able evals (JSON, not code).

Each packaged entry is a `{eval, commissions}` document. `avp init <key>`
**installs** its commissions into the portable library (`~/.avp/commissions/`,
skipping any id you already have) and writes the eval file *in place* as
`<key>.eval.json` so you can edit and commit it. The eval references the
commissions by id. `capitals` is the smallest entry (the default off a
non-interactive terminal): inline data, runs in seconds for pennies, no extra deps.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from avp.commission import Commission
from avp_cli import library


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    title: str
    description: str
    file: str
    needs: list[str] = field(default_factory=list)  # optional extras the config requires


@dataclass(frozen=True)
class ScaffoldResult:
    eval_path: Path
    installed: list[str]  # commission ids written into the library
    skipped: list[str]  # ids already present, left untouched


# Ordered for the picker. Each `file` is a `{eval, commissions}` JSON in this package.
ENTRIES: list[CatalogEntry] = [
    CatalogEntry(
        key="capitals",
        title="Capitals (structured extraction)",
        description="Tiny structured-extraction sample. Inline data, runs for pennies, no extra deps.",
        file="capitals.json",
    ),
    CatalogEntry(
        key="parsebench",
        title="ParseBench (tables)",
        description="PDF pages to HTML, scored on structural fidelity. Real LlamaIndex benchmark.",
        file="parsebench.json",
        needs=["parsebench"],
    ),
    CatalogEntry(
        key="custom",
        title="Custom (start from scratch)",
        description="A minimal real eval you fill in with your own task and commissions.",
        file="custom.json",
    ),
]


def get(key: str) -> CatalogEntry | None:
    return next((e for e in ENTRIES if e.key == key), None)


def load(entry: CatalogEntry) -> dict[str, Any]:
    """Parse the entry's packaged `{eval, commissions}` document."""
    return json.loads((files("avp_cli.catalog") / entry.file).read_text())


def _unique_eval_path(dest_dir: Path, key: str) -> Path:
    """`<dest>/<key>.eval.json`, or `<key>-2.eval.json`, `-3`, ... if taken.

    `avp init` is non-destructive: scaffolding a benchmark you already have writes
    a fresh, editable copy rather than clobbering or refusing.
    """
    target = dest_dir / f"{key}.eval.json"
    i = 2
    while target.exists():
        target = dest_dir / f"{key}-{i}.eval.json"
        i += 1
    return target


def scaffold(
    entry: CatalogEntry,
    dest_dir: Path,
    agents: list[str] | None = None,
    *,
    commissions_dir: Path | None = None,
) -> ScaffoldResult:
    """Install the entry's commissions into the library and write its eval file.

    The eval file goes to `<dest>/<key>.eval.json` (or a `-2`, `-3`, ... suffix if
    that name is taken) and references the commissions by id. Commissions go to the
    library; an id you already have is left untouched (reported in `skipped`).

    The eval's `commissions` block is taken verbatim from the entry when present
    (so an entry can bind commissions to agents via the `{agent: [ids]}` map);
    otherwise it defaults to a flat list of every installed id. When `agents` is
    given and the entry doesn't already bind agents via a map, they're pinned in
    an `"agents"` key so `avp eval run` targets them without `--agent`.
    """
    doc = load(entry)
    commissions: dict[str, Any] = doc["commissions"]  # {id: wire Commission}
    installed: list[str] = []
    skipped: list[str] = []
    for cid, spec in commissions.items():
        if library.exists(cid, commissions_dir=commissions_dir):
            skipped.append(cid)
        else:
            library.save(cid, Commission.model_validate(spec), commissions_dir=commissions_dir)
            installed.append(cid)

    target = _unique_eval_path(dest_dir, entry.key)
    eval_spec = doc["eval"]
    eval_doc: dict[str, Any] = {"name": eval_spec.get("name", entry.key)}
    binding = eval_spec.get("commissions", list(commissions.keys()))
    # A map binding names its agents in the keys; only pin a separate "agents"
    # key for the flat-list form.
    if agents and not isinstance(binding, dict):
        eval_doc["agents"] = agents
    eval_doc["dataset"] = eval_spec["dataset"]
    eval_doc["scorer"] = eval_spec["scorer"]
    eval_doc["commissions"] = binding
    target.write_text(json.dumps(eval_doc, indent=2) + "\n")
    return ScaffoldResult(eval_path=target, installed=installed, skipped=skipped)
