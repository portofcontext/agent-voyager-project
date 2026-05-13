"""`avp-conformance` CLI — the unified entry point for AVP wire-level verification.

Subcommands:
    avp-conformance run [--suite DIR | --case FILE]   — execute conformance cases
    avp-conformance validate [--suite DIR]            — schema-validate case files
    avp-conformance check-coverage                    — every event type has ≥1 case

Each subcommand discovers paths from a workspace root by walking up from the
CWD looking for `conformance/`. Override with explicit flags.
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

    Returns the first ancestor that contains `conformance/HARNESS.md`, or None.
    """
    cur = (start or Path.cwd()).resolve()
    while True:
        if (cur / "conformance" / "HARNESS.md").is_file():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


# Per-spec schema file locations (relative to repo root). Updated when a
# spec version bumps; the CLI walks these paths to load all schemas.
SPEC_SCHEMA_PATHS: dict[str, tuple[str, str]] = {
    "trajectory": ("trajectory", "v0.1"),
    "agent-descriptor": ("agent-descriptor", "v0.1"),
    "commission": ("commission", "v0.1-beta"),
    # resolver has no schema file; it's an RPC protocol.
}


def _spec_schema_files(root: Path) -> list[Path]:
    """Resolve each entry in SPEC_SCHEMA_PATHS to an absolute schema path."""
    return [
        root / "spec" / spec / version / f"{spec}.schema.json"
        for spec, (spec, version) in SPEC_SCHEMA_PATHS.items()
    ]


def _default_paths() -> tuple[Path | None, list[Path], Path | None]:
    """Resolve (cases_root, spec_schema_files, test_case_schema_path)."""
    root = _find_workspace_root()
    if root is None:
        return None, [], None
    return (
        root / "conformance",
        _spec_schema_files(root),
        root / "conformance" / "schema" / "test-case.schema.json",
    )


def _resolve_suite(arg: Path | None, default: Path | None) -> Path:
    if arg is not None:
        return arg
    if default is not None:
        return default
    print(
        "error: could not find conformance/ from CWD; pass --suite explicitly",
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
    default_suite, default_schema_files, default_test_case_schema = _default_paths()
    test_case_schema = args.test_case_schema or default_test_case_schema
    suite = _resolve_suite(args.suite, default_suite)
    schema_files = [Path(p) for p in args.schema_file] if args.schema_file else default_schema_files

    if test_case_schema is None or not schema_files:
        print(
            "error: could not locate spec schemas or conformance/schema/test-case.schema.json; "
            "pass --schema-file + --test-case-schema",
            file=sys.stderr,
        )
        return 2

    cases, failures = validate_suite(
        suite_dir=suite,
        spec_schema_files=schema_files,
        test_case_schema_path=test_case_schema,
    )
    if not cases:
        print(f"no cases found under {suite}", file=sys.stderr)
        return 2

    failed_paths = {f.path for f in failures}
    for path in cases:
        rel = path.relative_to(suite)
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
    default_suite, default_schema_files, _ = _default_paths()
    suite = _resolve_suite(args.suite, default_suite)

    if args.schema:
        trajectory_schema = args.schema
    else:
        # Coverage uses the Trajectory schema specifically (event types live there).
        trajectory_schema = next(
            (p for p in default_schema_files if p.name == "trajectory.schema.json"), None
        )

    if trajectory_schema is None:
        print(
            "error: could not find spec/trajectory/<version>/trajectory.schema.json; "
            "pass --schema explicitly",
            file=sys.stderr,
        )
        return 2

    report = check_coverage(schema_path=trajectory_schema, cases_dir=suite)

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
        "\nadd a case under conformance/<spec>/<version>/cases/ that asserts on the missing\n"
        "type(s), or add to DEFERRED_COVERAGE in avp.conformance.coverage with a reason if\n"
        "no v0.1 agent emits it.",
        file=sys.stderr,
    )
    return 1


# ── Top-level dispatch ───────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avp-conformance",
        description="AVP wire-level conformance: run cases, validate them, check coverage.",
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
        "--schema-file",
        action="append",
        help="schema file to register in the validation registry (repeatable; "
        "auto-discovered from spec/<spec>/<version>/<spec>.schema.json by default)",
    )
    p_val.add_argument(
        "--test-case-schema",
        type=Path,
        help="path to conformance/schema/test-case.schema.json",
    )
    p_val.set_defaults(func=_cmd_validate)

    p_cov = sub.add_parser(
        "check-coverage",
        help="every event type declared in the trajectory schema has ≥1 conformance case",
    )
    p_cov.add_argument("--suite", type=Path, help="directory of *.json cases (recursive)")
    p_cov.add_argument(
        "--schema", type=Path, help="path to trajectory.schema.json (auto-discovered by default)"
    )
    p_cov.set_defaults(func=_cmd_check_coverage)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
