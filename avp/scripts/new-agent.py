#!/usr/bin/env python3
"""Scaffold a new AVP agent from `agents/_template/<lang>/`.

    make new-agent NAME=avp-mastra          # Python
    make new-agent-rust NAME=avp-mastra     # Rust

Copies the template to `agents/<NAME>/<LANG>/`, renames the package, the
agent name, and the manifest command, and registers the agent everywhere the
template is registered: the uv workspace (members, root dependencies,
sources), `make test` (`TEST_PKGS`), `make conformance`, and ruff's
first-party list (Python). The result passes its tests and `ping` /
`describe` before you change a line; then replace its stand-in harness.

`NAME` is the distribution / crate name and the agent's `AGENT_NAME` (the key
Commissions use in their per-agent allow-lists), e.g. `avp-mastra`.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMPLATE_NAME = "avp-agent-template"
TEMPLATE_PKG = "avp_agent_template"


def _edit(path: Path, *pairs: tuple[str, str]) -> None:
    text = path.read_text()
    for old, new in pairs:
        if old not in text:
            sys.exit(f"error: {path.relative_to(REPO)}: anchor not found: {old.strip()!r}")
        text = text.replace(old, new, 1)
    path.write_text(text)


def _rewrite_tree(root: Path, name: str, pkg: str) -> None:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".rs", ".toml", ".json", ".md"}:
            text = path.read_text()
            path.write_text(text.replace(TEMPLATE_PKG, pkg).replace(TEMPLATE_NAME, name))


def scaffold_python(name: str, dest: Path) -> None:
    pkg = name.replace("-", "_")
    shutil.copytree(
        REPO / "agents/_template/python",
        dest,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.egg-info"),
    )
    (dest / "src" / TEMPLATE_PKG).rename(dest / "src" / pkg)
    _rewrite_tree(dest, name, pkg)
    rel = dest.relative_to(REPO).as_posix()
    _edit(
        REPO / "pyproject.toml",
        ('    "avp-agent-template",\n', f'    "avp-agent-template",\n    "{name}",\n'),
        ('    "agents/_template/python",\n', f'    "agents/_template/python",\n    "{rel}",\n'),
        (
            "avp-agent-template = { workspace = true }\n",
            f"avp-agent-template = {{ workspace = true }}\n{name} = {{ workspace = true }}\n",
        ),
    )
    _edit(REPO / "ruff.toml", ('"avp_agent_template", ', f'"avp_agent_template", "{pkg}", '))
    _register_make(name, rel, test_pkg=True)


def scaffold_rust(name: str, dest: Path) -> None:
    shutil.copytree(
        REPO / "agents/_template/rust",
        dest,
        ignore=shutil.ignore_patterns("target", "Cargo.lock"),
    )
    _rewrite_tree(dest, name, name.replace("-", "_"))
    _register_make(name, dest.relative_to(REPO).as_posix(), test_pkg=False)


def _register_make(name: str, rel: str, *, test_pkg: bool) -> None:
    var = re.sub(r"[^A-Z0-9]", "_", name.upper()) + "_MANIFEST"
    pairs = [
        (
            "TEMPLATE_MANIFEST := agents/_template/python/avp-conformance.json\n",
            "TEMPLATE_MANIFEST := agents/_template/python/avp-conformance.json\n"
            f"{var} := {rel}/avp-conformance.json\n",
        ),
        (
            "\t@$(UV) run avp-conformance describe --agent $(TEMPLATE_MANIFEST)\n",
            "\t@$(UV) run avp-conformance describe --agent $(TEMPLATE_MANIFEST)\n"
            f'\t@printf "\\n\\033[1;36m── {name} ──\\033[0m\\n"\n'
            f"\t@$(UV) run avp-conformance ping --agent $({var})\n"
            f"\t@$(UV) run avp-conformance describe --agent $({var})\n",
        ),
    ]
    if test_pkg:
        pairs.append(
            ("\tagents/_template/python \\\n", f"\tagents/_template/python \\\n\t{rel} \\\n")
        )
    _edit(REPO / "Makefile", *pairs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("name", help="distribution / crate name and AGENT_NAME, e.g. avp-mastra")
    parser.add_argument("--lang", choices=["python", "rust"], default="python")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9]*(-[a-z0-9]+)*", args.name):
        sys.exit("error: NAME must be lowercase kebab-case, e.g. avp-mastra")
    dest = REPO / "agents" / args.name / args.lang
    if dest.exists():
        sys.exit(f"error: {dest.relative_to(REPO)} already exists")
    (scaffold_python if args.lang == "python" else scaffold_rust)(args.name, dest)
    rel = dest.relative_to(REPO)
    print(f"created {rel}")
    print("next:")
    if args.lang == "python":
        print("  uv sync")
        print(f"  (cd {rel} && uv run pytest -q)")
    else:
        print(f"  (cd {rel} && cargo test)")
    print(f"  uv run avp-conformance ping --agent {rel}/avp-conformance.json")
    print("  then replace the stand-in harness: see agents/_template/README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
