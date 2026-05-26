"""`avp-conformance` CLI — the unified entry point for AVP wire-level verification.

Subcommands:
    avp-conformance run [--suite DIR | --case FILE]   — execute conformance cases
    avp-conformance validate [--suite DIR]            — schema-validate case files
    avp-conformance check-coverage                    — every event type has ≥1 case

Each subcommand discovers paths from a workspace root by walking up from the
CWD looking for `conformance/v0.1/`. Override with explicit flags.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from avp.conformance.coverage import check_coverage
from avp.conformance.harness import run_case, run_suite
from avp.conformance.validate import validate_suite

# ── Workspace-root discovery ─────────────────────────────────────────────────


def _find_workspace_root(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default CWD) looking for the conformance dir.

    Returns the first ancestor that contains `conformance/v0.1/`, or None.
    """
    cur = (start or Path.cwd()).resolve()
    while True:
        if (cur / "conformance" / "v0.1").is_dir():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _default_paths() -> tuple[Path | None, Path | None, Path | None]:
    """Resolve (suite_dir, schema_path, test_case_schema_path) from CWD walk-up."""
    root = _find_workspace_root()
    if root is None:
        return None, None, None
    return (
        root / "conformance" / "v0.1" / "cases",
        root / "spec" / "v0.1" / "avp.schema.json",
        root / "conformance" / "v0.1" / "schema" / "test-case.schema.json",
    )


def _resolve_suite(arg: Path | None, default: Path | None) -> Path:
    if arg is not None:
        return arg
    if default is not None:
        return default
    print(
        "error: could not find conformance/v0.1/ from CWD; pass --suite explicitly",
        file=sys.stderr,
    )
    raise SystemExit(2)


# ── Subcommand: run ──────────────────────────────────────────────────────────


def _cmd_run(args: argparse.Namespace) -> int:
    if args.case:
        results = [run_case(args.case)]
    else:
        default_suite, _, _ = _default_paths()
        suite = _resolve_suite(args.suite, default_suite)
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
                    print(f"        {ev.get('source', '?'):>10}  {ev.get('type', '?')}  {ev}")
    print()
    print(f"{len(results) - fails} / {len(results)} cases passed")
    return 0 if fails == 0 else 1


# ── Subcommand: validate ─────────────────────────────────────────────────────


def _cmd_validate(args: argparse.Namespace) -> int:
    default_suite, _, default_test_case_schema = _default_paths()
    root = _find_workspace_root()
    spec_dir = (
        args.spec_dir if args.spec_dir is not None else (root / "spec" / "v0.1" if root else None)
    )
    test_case_schema = args.test_case_schema or default_test_case_schema
    suite = _resolve_suite(args.suite, default_suite)

    if spec_dir is None or test_case_schema is None:
        print(
            "error: could not find spec/v0.1/ or conformance/v0.1/schema/; pass --spec-dir + --test-case-schema",
            file=sys.stderr,
        )
        return 2

    cases, failures = validate_suite(
        suite_dir=suite, spec_dir=spec_dir, test_case_schema_path=test_case_schema
    )
    if not cases:
        print(f"no cases found under {suite}", file=sys.stderr)
        return 2

    failed_paths = {f.path for f in failures}
    for path in cases:
        rel = path.relative_to(suite.parent)
        if path in failed_paths:
            print(f"FAIL  {rel}")
            for f in failures:
                if f.path == path:
                    for e in f.errors:
                        print(f"      {e}")
        else:
            print(f"PASS  {rel}")

    print()
    print(f"{len(cases) - len(failures)} / {len(cases)} cases valid")
    return 0 if not failures else 1


# ── Subcommand: check-coverage ───────────────────────────────────────────────


def _cmd_check_coverage(args: argparse.Namespace) -> int:
    default_suite, default_schema, _ = _default_paths()
    schema = args.schema or default_schema
    suite = _resolve_suite(args.suite, default_suite)

    if schema is None:
        print(
            "error: could not find spec/v0.1/avp.schema.json; pass --schema explicitly",
            file=sys.stderr,
        )
        return 2

    report = check_coverage(schema_path=schema, cases_dir=suite)

    if report.ok:
        msg = f"✓ {len(report.declared - set(report.deferred))} of {len(report.declared)} event types covered"
        if report.deferred:
            msg += f"; {len(report.deferred)} deferred ({', '.join(sorted(report.deferred))})"
        print(msg)
        return 0

    print(
        f"✗ {len(report.uncovered)} event types have NO conformance case:",
        file=sys.stderr,
    )
    for name in sorted(report.uncovered):
        print(f"    - {name}", file=sys.stderr)
    print(
        "\nadd a case under conformance/v0.1/cases/ that asserts on the missing type(s),\n"
        "or add to DEFERRED_COVERAGE in avp.conformance.coverage with a reason if no\n"
        "v0.1 agent emits it.",
        file=sys.stderr,
    )
    return 1


# ── Top-level dispatch ───────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avp-conformance",
        description="AVP v0.1 wire-level conformance: run cases, validate them, check coverage.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="execute conformance cases against the reference agent")
    g = p_run.add_mutually_exclusive_group()
    g.add_argument("--case", type=Path, help="run a single case file")
    g.add_argument("--suite", type=Path, help="directory of *.json cases (recursive)")
    p_run.add_argument("-v", "--verbose", action="store_true", help="dump trajectory on failure")
    p_run.set_defaults(func=_cmd_run)

    p_val = sub.add_parser("validate", help="schema-validate every case file")
    p_val.add_argument("--suite", type=Path, help="directory of *.json cases (recursive)")
    p_val.add_argument(
        "--spec-dir", type=Path, help="path to spec/v0.1/ (auto-discovered by default)"
    )
    p_val.add_argument(
        "--test-case-schema",
        type=Path,
        help="path to conformance/v0.1/schema/test-case.schema.json",
    )
    p_val.set_defaults(func=_cmd_validate)

    p_cov = sub.add_parser(
        "check-coverage",
        help="every event type declared in the schema has ≥1 conformance case asserting on it",
    )
    p_cov.add_argument("--suite", type=Path, help="directory of *.json cases (recursive)")
    p_cov.add_argument("--schema", type=Path, help="path to spec/v0.1/avp.schema.json")
    p_cov.set_defaults(func=_cmd_check_coverage)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
