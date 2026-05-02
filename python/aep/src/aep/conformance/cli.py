"""`aep-conformance` CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aep.conformance.harness import run_case, run_suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aep-conformance",
        description="Run AEP v0.1 conformance cases against the reference Python runner.",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--case", type=Path, help="run a single case file")
    g.add_argument("--suite", type=Path, help="run every *.json under this directory recursively")
    parser.add_argument("-v", "--verbose", action="store_true", help="dump trajectory on failure")
    args = parser.parse_args(argv)

    if args.case:
        results = [run_case(args.case)]
    else:
        results = run_suite(args.suite)

    if not results:
        print(f"no cases found under {args.suite or args.case}", file=sys.stderr)
        return 2

    fails = 0
    for r in results:
        if r.passed:
            print(f"PASS  {r.case_id}  ({r.duration_ms}ms)")
        else:
            fails += 1
            print(f"FAIL  {r.case_id}  ({r.duration_ms}ms)")
            for f in r.failures:
                print(f"        {f.label}: {f.detail}")
            if args.verbose:
                print("      trajectory:")
                for ev in r.trajectory[-30:]:  # last 30 events
                    print(f"        {ev.get('source', '?'):>10}  {ev.get('type', '?')}  {ev}")
    print()
    print(f"{len(results) - fails} / {len(results)} cases passed")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
