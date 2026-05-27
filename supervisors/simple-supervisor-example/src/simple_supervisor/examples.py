"""Run the simple-supervisor real-LLM examples in sequence.

Backs the `simple-supervisor examples` subcommand. Resolves API key from the
environment or `~/.anthropic-key`, discovers the examples/ directory relative
to the package, and shells out to `uv run python <example>` so each example
runs in its own process (which is what the README documents anyway).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# package root → examples/ lives next to src/ in the repo layout
_PKG_ROOT = Path(__file__).resolve().parent
_REPO_ROOT_HINT = _PKG_ROOT.parent.parent  # src/simple_supervisor → src → package root


def _examples_dir() -> Path:
    """Find the examples/ directory.

    Two layouts to support:
      1. Editable install from the workspace (most common): the package is
         under python/supervisors/simple-supervisor-example/src/, examples/
         lives at python/supervisors/simple-supervisor-example/examples/
      2. Override via $AVP_EXAMPLES_DIR for unusual layouts
    """
    override = os.environ.get("AVP_EXAMPLES_DIR")
    if override:
        return Path(override).resolve()
    candidate = _REPO_ROOT_HINT / "examples"
    if candidate.is_dir():
        return candidate.resolve()
    raise FileNotFoundError(
        f"could not find examples/ at {candidate}; set AVP_EXAMPLES_DIR to override"
    )


_EXAMPLES: dict[str, tuple[str, str, dict[str, str]]] = {
    "01": (
        "01_anthropic_cost_bounded.py",
        "read-only inspection (driver pattern, ~$0.001)",
        {},
    ),
    "03": (
        "03_claude_code_audited.py",
        "audited Claude Code session (observer pattern, ~$0.10)",
        {"USE_REAL_SDK": "1"},
    ),
    "05": (
        "05_anthropic_subagent_delegation.py",
        "subagent delegation (driver pattern, ~$0.01)",
        {},
    ),
    "06": (
        "06_anthropic_traced_client.py",
        "traced Anthropic client (drop-in instrumentation, ~$0.01)",
        {},
    ),
    "07": (
        "07_claude_agent_traced_client.py",
        "traced Claude Agent SDK client (~$0.05)",
        {"USE_REAL_SDK": "1"},
    ),
}


def _resolve_api_key() -> str | None:
    """Return the API key, or None if neither env var nor ~/.anthropic-key has one."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    keyfile = Path.home() / ".anthropic-key"
    if keyfile.is_file():
        return keyfile.read_text().strip()
    return None


def run_examples(selected: list[str] | None = None) -> int:
    """Run the requested examples (or all three if `selected` is None/empty)."""
    if not selected:
        selected = ["01", "03", "05", "06", "07"]

    # Validate before doing any work.
    for n in selected:
        if n not in _EXAMPLES:
            print(
                f"error: unknown example '{n}' (valid: {', '.join(sorted(_EXAMPLES))})",
                file=sys.stderr,
            )
            return 2

    api_key = _resolve_api_key()
    if api_key is None:
        print(
            "error: ANTHROPIC_API_KEY not set and ~/.anthropic-key not readable\n"
            "       set the env var or write your key to ~/.anthropic-key (chmod 600)",
            file=sys.stderr,
        )
        return 2

    examples_dir = _examples_dir()
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = api_key

    results: list[tuple[str, int]] = []  # (example_id, exit_code)

    for n in selected:
        file_name, label, extra_env = _EXAMPLES[n]
        print()
        print("════════════════════════════════════════════════════════════════════")
        print(f"  Example {n} — {label}")
        print("════════════════════════════════════════════════════════════════════")
        print()

        run_env = dict(env)
        run_env.update(extra_env)
        rc = subprocess.run(
            [sys.executable, str(examples_dir / file_name)],
            env=run_env,
        ).returncode
        results.append((n, rc))

    # Aggregate report — each example self-validated (`_validate_outcome`)
    # and exited 0 on PASS, non-zero on FAIL.
    print()
    print("════════════════════════════════════════════════════════════════════")
    print("  Summary")
    print("════════════════════════════════════════════════════════════════════")
    passed = sum(1 for _, rc in results if rc == 0)
    total = len(results)
    for n, rc in results:
        status = "PASS" if rc == 0 else f"FAIL (exit {rc})"
        print(f"  example {n}: {status}")
    print(f"\n{passed} / {total} examples passed")
    return 0 if passed == total else 1
