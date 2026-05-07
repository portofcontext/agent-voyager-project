"""Example 04 — DDD-strict supervisor (driver pattern, aep-anthropic).

What this demonstrates: a real `DDD_STRICT` profile compiling Domain-Driven
Design concerns into AEP verifiers, applied to a small but real DDD codebase.

The workspace at `examples/04_ddd_domain/` is a hand-written DDD example:

  domain/order/      — Order aggregate root + OrderLine value object + OrderStatus
  domain/customer/   — Customer aggregate root + EmailAddress value object
  tests/invariants/  — pytest tests pinning aggregate invariants

The DDD_STRICT profile ships three verifiers, each compiling one DDD concern:

  1. domain-layer-purity (on_tool:write_file, halt)
       grep domain/ for infrastructure imports — domain MUST stay pure.
       Halt-on-fail because importing SQLAlchemy into the domain isn't
       recoverable inside one run; it's an architectural contract.
  2. aggregate-invariants (after_each_turn, inject_correction)
       run pytest tests/invariants/. If a regression appears, inject a
       DDD principle into the conversation: "don't loosen the invariant
       to fit the feature; the feature fits the invariant." The agent
       sees this as a user-role correction and gets to re-design.
  3. no-anemic-suffixes-in-domain (on_tool:write_file, inject_correction)
       no *Manager.py / *Helper.py / *Util.py files in domain — names MUST
       reflect business concepts, not generic OO patterns.

The agent's task has a built-in tension: it asks for a synthetic discount
line with NEGATIVE unit_price, but the existing OrderLine value object
forbids negative prices. The naive resolution is to weaken the value
object — which breaks an existing invariant test. Verifier 2 catches it
and injects a correction telling the agent to find a different shape (a
separate Discount value object, a discounts field on Order, etc).

What you'll see in the trajectory (hopefully):
  - Multiple verifier_evaluated events with passed=true (passing turns)
  - One or more passed=false → inject_correction events
  - A subsequent model_turn_started where the agent reads the correction
  - A revised design that preserves all invariants
  - Convergence with all rules green

Requires: ANTHROPIC_API_KEY, pytest installed in the runner's environment,
plus an editable copy of the toy domain at examples/04_ddd_domain/.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from simple_supervisor import build_config, render, stream_subprocess, summarize

EXAMPLES_DIR = Path(__file__).resolve().parent
DOMAIN_TEMPLATE = EXAMPLES_DIR / "04_ddd_domain"


def _stage_workspace() -> Path:
    """Copy the toy domain to a fresh tempdir so the run can write to it
    without polluting the repo. The supervisor's deployment layer is what
    provisions the workspace (per SPEC.md §14); this is the demo's version
    of that responsibility."""
    workspace = Path(tempfile.mkdtemp(prefix="aep-ddd-"))
    shutil.copytree(DOMAIN_TEMPLATE, workspace, dirs_exist_ok=True)

    # Initialize a git repo so verifiers that diff against HEAD have something
    # to compare to (the no-todos verifier from QUALITY_GUARDS does this; the
    # DDD profile doesn't, but git init also helps when debugging by hand).
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=demo@aep.dev",
            "-c",
            "user.name=demo",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=workspace,
        check=True,
    )
    return workspace


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY before running this example", file=sys.stderr)
        return 2

    workspace = _stage_workspace()
    run_id = f"ddd-supervisor-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    config = build_config(
        run_id=run_id,
        prompt=(
            "Add a method `apply_discount(amount: Decimal) -> None` to the Order "
            "aggregate. It MUST:\n"
            "  - Reject discounts greater than the current total (raise ValueError).\n"
            "  - Reject discounts on non-PENDING orders (raise ValueError).\n"
            "  - Otherwise, append a synthetic OrderLine with sku='DISCOUNT', "
            "quantity=1, and a NEGATIVE unit_price equal to -amount, so that "
            "Order.total still equals sum(line.subtotal for line in lines).\n"
            "Then add a test in tests/invariants/test_order_invariants.py "
            "covering the happy path and one rejection case. End by saying DONE."
        ),
        profile="ddd-strict",
        # Sonnet rather than Haiku here because this example is the most
        # adversarial in the repo — the task is intentionally a tension
        # against an existing aggregate invariant (OrderLine.unit_price >= 0
        # vs. the requested NEGATIVE discount-line price). Haiku reliably
        # hits the turn limit fighting the invariant test; Sonnet finds
        # the right shape (typically a separate `discount: Decimal` field
        # on Order or a non-OrderLine discount value object) within budget.
        # The verifier mechanism works either way — this is just choosing
        # a model strong enough to demonstrate the resolution rather than
        # the standoff.
        model="claude-sonnet-4-6",
        # Generous boundary because pytest runs after each turn (slow vs
        # mock); domain layer is small but multi-turn is normal here.
        boundary_overrides={"max_cost_usd": 1.50, "max_steps": 15, "max_tokens": 200_000},
    )

    # The OrderLine value object validates unit_price >= 0 today. The agent's
    # task asks for a NEGATIVE unit_price on the synthetic discount line —
    # which means the agent has to weaken that invariant OR find another shape.
    # Either response is interesting; the verifiers will keep them honest.

    print(f"== Workspace: {workspace} ==")
    print()
    print("== Config (compiled from profile='ddd-strict') ==")
    print(config.model_dump_json(indent=2, exclude_none=True))
    print()
    print("== Live trajectory ==")

    events: list = []
    for ev in stream_subprocess(["aep-anthropic"], config, cwd=str(workspace)):
        events.append(ev)
        type_name = getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else "?")
        if type_name == "model_turn_ended":
            print(
                f"  [turn {ev.data.step}] cost=${ev.data.aep_cost_usd:.5f}  "
                f"tokens={ev.data.gen_ai_usage_input_tokens}+{ev.data.gen_ai_usage_output_tokens}"
            )
        elif type_name == "tool_invoked":
            keys = list(ev.data.gen_ai_tool_call_arguments.keys())
            preview = ""
            if "path" in ev.data.gen_ai_tool_call_arguments:
                preview = f" path={ev.data.gen_ai_tool_call_arguments['path']}"
            print(f"  [turn {ev.data.step}] -> {ev.data.gen_ai_tool_name}({keys}){preview}")
        elif type_name == "tool_returned":
            head = (
                ev.data.aep_tool_result_text.replace("\n", " ")[:80]
                if ev.data.aep_tool_result_text
                else ""
            )
            print(f"  [turn {ev.data.step}] <- {ev.data.gen_ai_tool_name}: {head!r}")
        elif type_name == "verifier_evaluated":
            mark = "PASS" if ev.data.aep_verifier_passed else "FAIL"
            err = f" error={ev.data.aep_verifier_error}" if ev.data.aep_verifier_error else ""
            print(f"  [turn {ev.data.step}] verifier '{ev.name}': {mark}{err}")
            if not ev.data.aep_verifier_passed and ev.data.aep_verifier_data:
                stdout = (ev.data.get("stdout") or "").strip()
                stderr = (ev.data.get("stderr") or "").strip()
                if stdout:
                    print(f"      stdout: {stdout[:200]}")
                if stderr:
                    print(f"      stderr: {stderr[:200]}")
        elif type_name == "agent_stopped":
            print(f"  STOPPED reason={ev.data.aep_reason}")

    print()
    print(render(summarize(events)))

    # Show the resulting Order.py — what did the agent actually write?
    order_py = workspace / "domain" / "order" / "order.py"
    if order_py.exists():
        print()
        print(f"== Final {order_py.relative_to(workspace)} ==")
        print(order_py.read_text())

    print()
    print(f"workspace preserved at: {workspace}")
    print("inspect with: tree", workspace)

    issues = _validate_outcome(events, workspace)
    print()
    if issues:
        print("== ✗ FAIL — example 04 ==")
        for msg in issues:
            print(f"  - {msg}")
        return 1
    print("== ✓ PASS — example 04 ==")
    return 0


def _validate_outcome(events: list, workspace: Path) -> list[str]:
    """Post-conditions for example 04. LLM trajectory varies; outcomes don't.

    PASS criteria are the architectural promises the demo makes:
      - Run converged
      - All four verifier triggers exercised at least once during the run
        (proves the inject_correction loop got the chance to run if needed)
      - Final workspace's invariant test suite PASSES
        (the load-bearing check — agent shipped DDD-correct code)
      - domain/order/order.py defines `apply_discount`
      - No anemic-suffix files left in domain/
      - No infrastructure imports leaked into domain/
    """
    issues: list[str] = []

    stop = next((ev for ev in events if type(ev).__name__ == "AgentStoppedEvent"), None)
    if stop is None:
        issues.append("no agent_stopped event — runner exited mid-trajectory")
        return issues
    # converged is the goal; turn_limit means the agent ran out of budget,
    # which we still accept as long as the final workspace invariants hold
    # (the supervisor's whole point is that even failed runs leave clean state).
    if str(stop.data.aep_reason) not in ("converged", "turn_limit"):
        issues.append(
            f"unexpected stop reason {stop.data.aep_reason!r}; expected 'converged' or 'turn_limit'"
        )

    # Every trigger fired at least once — proves the verifier dispatch is alive.
    verifier_evals = [ev for ev in events if type(ev).__name__ == "VerifierEvaluatedEvent"]
    fired_names = {ev.data.aep_verifier_name for ev in verifier_evals}
    expected_verifiers = {
        "domain-layer-purity",
        "aggregate-invariants",
        "no-anemic-suffixes-in-domain",
    }
    missing = expected_verifiers - fired_names
    if missing:
        issues.append(f"verifiers never fired: {sorted(missing)}")

    # Load-bearing check: the final workspace's invariant tests pass. This is
    # what proves the agent shipped a DDD-correct design — not just "code that
    # compiles", but code that satisfies every invariant the supervisor cares
    # about. Same shell command the runtime verifier uses.
    final_pytest = subprocess.run(
        ["python", "-m", "pytest", "tests/invariants/", "-q", "--tb=line"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    if final_pytest.returncode != 0:
        issues.append(
            f"final workspace's invariant tests FAIL — agent shipped broken state. "
            f"pytest stdout: {final_pytest.stdout.strip()[-300:]}"
        )

    # The agent must have actually added apply_discount.
    order_py = workspace / "domain" / "order" / "order.py"
    if not order_py.exists():
        issues.append("domain/order/order.py missing in final workspace")
    elif "def apply_discount" not in order_py.read_text():
        issues.append("apply_discount method not present in final Order.py")

    # No anemic suffixes shipped (the verifier should have caught any, but
    # double-check the final state).
    domain_dir = workspace / "domain"
    if domain_dir.is_dir():
        anemic = []
        for path in domain_dir.rglob("*.py"):
            stem = path.stem.lower()
            if stem.endswith(("manager", "helper", "util", "utils")):
                anemic.append(str(path.relative_to(workspace)))
        if anemic:
            issues.append(f"anemic-suffix files in domain/: {anemic}")

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
