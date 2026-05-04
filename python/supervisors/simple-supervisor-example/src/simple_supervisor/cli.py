"""`simple-supervisor` CLI — quick demo entry point.

Usage:
    simple-supervisor list-profiles
    simple-supervisor show-config --profile ddd-strict --prompt "..."
"""

from __future__ import annotations

import argparse
import sys

from simple_supervisor.builder import build_config
from simple_supervisor.profiles import PRESETS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simple-supervisor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-profiles", help="List available profile presets")

    p_show = sub.add_parser("show-config", help="Render a Config from a profile + prompt")
    p_show.add_argument("--profile", default="dev-loose", choices=sorted(PRESETS))
    p_show.add_argument("--prompt", required=True)
    p_show.add_argument("--run-id", default="demo-run")
    p_show.add_argument("--model", default="claude-sonnet-4-6")

    args = parser.parse_args(argv)

    if args.cmd == "list-profiles":
        for name, p in PRESETS.items():
            print(f"{name}")
            print(f"  {p.description}")
            print(f"  allowed_tools: {p.allowed_tools}")
            print(f"  boundary: {p.boundary}")
            print(f"  verifiers: {[v['name'] for v in p.verifiers]}")
            print()
        return 0

    if args.cmd == "show-config":
        cfg = build_config(
            run_id=args.run_id,
            prompt=args.prompt,
            profile=args.profile,
            model=args.model,
        )
        print(cfg.model_dump_json(indent=2, exclude_none=True))
        return 0

    parser.error("unreachable")
    return 2


if __name__ == "__main__":
    sys.exit(main())
