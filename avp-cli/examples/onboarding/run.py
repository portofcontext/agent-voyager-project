#!/usr/bin/env python3
"""Execute prepared onboarding trials through the ordinary AVP CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from build_commissions import write_json
from verify import verify

from avp_cli import paths
from avp_cli.agent import read_trajectory
from avp_cli.observability import summarize


def execute(
    batch: Path, *, agents: set[str], strategies: set[str], timeout: int, max_cost: float
) -> list[dict]:
    plan = json.loads((batch / "plan.json").read_text())
    result_path = batch / "results.json"
    records_dir = batch / "records"
    records_dir.mkdir(exist_ok=True)
    if result_path.exists() and not any(records_dir.glob("*.json")):
        for record in json.loads(result_path.read_text()):
            write_json(records_dir / f"{record['id']}.json", record)
    results = [json.loads(p.read_text()) for p in sorted(records_dir.glob("*.json"))]
    finished = {r["id"] for r in results}
    spent = sum(r.get("outer_cost_usd", 0) + r.get("child_cost_usd", 0) for r in results)
    for trial in plan["trials"]:
        if (
            trial["id"] in finished
            or (agents and trial["agent"] not in agents)
            or (strategies and trial["strategy"] not in strategies)
        ):
            continue
        if spent >= max_cost:
            print(f"Stopped between trials at ${spent:.4f} reported cost.", flush=True)
            break
        cid, tid = trial["commission"], trial["id"]
        library = paths.commissions_dir()
        library.mkdir(parents=True, exist_ok=True)
        dest = library / f"{cid}.json"
        content = (batch / "commissions" / dest.name).read_bytes()
        if dest.exists() and dest.read_bytes() != content:
            raise ValueError(f"refusing to overwrite different Commission: {dest}")
        dest.write_bytes(content)
        out = paths.runs_dir() / tid
        if out.exists():
            raise ValueError(f"trial workspace already exists: {out}; prepare a new batch")
        record = {**trial, "runtime": "opensandbox", "out": str(out)}
        print(f"Running {trial['agent']} / {trial['strategy']} / {trial['repeat']}", flush=True)
        start = time.monotonic()
        with (batch / f"{tid}.log").open("w") as log:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "avp_cli.cli",
                    "eval",
                    "run",
                    str(batch / "evals" / f"{tid}.json"),
                    "--runtime",
                    "opensandbox",
                    "--env",
                    str(batch / "environment.json"),
                    "--name",
                    tid,
                    "--out",
                    str(out),
                    "--json",
                    str(batch / f"{tid}.board.json"),
                    "--timeout",
                    str(timeout),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )
        record.update(exit_code=proc.returncode, wall_seconds=round(time.monotonic() - start, 2))
        cost, turns, tokens, errors = 0.0, 0, 0, []
        for path in out.glob("*.ndjson"):
            try:
                s = summarize(read_trajectory(path))
                cost += s.total_cost_usd
                turns += s.total_turns
                tokens += s.total_tokens
                errors.extend(s.errors)
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        record.update(
            outer_cost_usd=cost, outer_turns=turns, outer_tokens=tokens, outer_errors=errors
        )
        record.update(verify(out / "workspace", plan, trial["model"]))
        if proc.returncode:
            record["passed"] = False
        results.append(record)
        # Each trial is the durable record. Disjoint --agents subsets may run
        # concurrently without overwriting one another's results.
        write_json(records_dir / f"{tid}.json", record)
        write_json(
            result_path, [json.loads(p.read_text()) for p in sorted(records_dir.glob("*.json"))]
        )
        spent += cost + record["child_cost_usd"]
        print(
            f"  {'PASS' if record['passed'] else 'FAIL'}; ${cost + record['child_cost_usd']:.4f} reported; {record['wall_seconds']}s",
            flush=True,
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--agents", default="", help="Comma-separated subset; default all")
    parser.add_argument("--strategies", default="", help="Comma-separated subset; default all")
    parser.add_argument("--timeout", type=int, default=900, help="Seconds per outer agent run")
    parser.add_argument(
        "--max-reported-cost",
        type=float,
        default=25,
        help="Stop between trials at this reported cost; not a hard billing cap",
    )
    args = parser.parse_args()
    execute(
        args.batch.resolve(),
        agents=set(filter(None, args.agents.split(","))),
        strategies=set(filter(None, args.strategies.split(","))),
        timeout=args.timeout,
        max_cost=args.max_reported_cost,
    )
