"""`avp-claude-agent-conformance` CLI — run the v0.1 conformance suite
against `ClaudeAgentTranslator`.

Mirrors `avp-conformance run` but drives the observer-pattern translator
instead of the reference `AVPAgent`. Same case files, same matcher
language, parallel reporting format.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from avp_claude_agent.conformance import run_case, run_suite


def _find_workspace_root(start: Path | None = None) -> Path | None:
    cur = (start or Path.cwd()).resolve()
    while True:
        if (cur / "conformance" / "v0.1").is_dir():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _resolve_suite(arg: Path | None) -> Path:
    if arg is not None:
        return arg
    root = _find_workspace_root()
    if root is None:
        print(
            "error: could not find conformance/v0.1/ from CWD; pass --suite explicitly",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return root / "conformance" / "v0.1" / "cases"


def _cmd_run(args: argparse.Namespace) -> int:
    if args.case:
        results = [run_case(args.case)]
    else:
        suite = _resolve_suite(args.suite)
        results = run_suite(suite)

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
                for ev in r.trajectory[-30:]:
                    print(f"        {ev.get('source', '?'):>10}  {ev.get('type', '?')}")
    print()
    print(f"{len(results) - fails} / {len(results)} cases passed")
    return 0 if fails == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avp-claude-agent-conformance",
        description="Run v0.1 conformance cases against ClaudeAgentTranslator.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="execute conformance cases")
    g = p_run.add_mutually_exclusive_group()
    g.add_argument("--case", type=Path, help="run a single case file")
    g.add_argument("--suite", type=Path, help="directory of *.json cases (recursive)")
    p_run.add_argument("-v", "--verbose", action="store_true", help="dump trajectory on failure")
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
