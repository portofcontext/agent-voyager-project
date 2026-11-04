#!/usr/bin/env python3
"""Prepare ordinary one-cell AVP evaluations; vary only onboarding inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from avp.commission import Commission

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STRATEGIES = ("repo", "prompt", "cli-docs", "skill", "skill-invoked")
MODELS = {
    "claude-code": "anthropic/claude-sonnet-4-6",
    "codex": "openai/gpt-5.5",
    "pi": "anthropic/claude-sonnet-4-6",
}
CASES = [
    {"id": "sum", "question": "What is 17 + 25?", "expected": {"answer": 42}},
    {"id": "product", "question": "What is 9 times 7?", "expected": {"answer": 63}},
    {"id": "difference", "question": "What is 100 minus 28?", "expected": {"answer": 72}},
]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp.write(json.dumps(value, indent=2) + "\n")
    Path(tmp.name).replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(
    out: Path,
    wheel: Path,
    *,
    repetitions: int = 1,
    seed: int = 42,
    models: dict[str, str] | None = None,
    agents: dict[str, str] | None = None,
) -> dict:
    models = {**MODELS, **(models or {})}
    if set(models) != set(MODELS):
        raise ValueError("model overrides must name codex, claude-code, or pi")
    agents = {**{name: name for name in MODELS}, **(agents or {})}
    if set(agents) != set(MODELS):
        raise ValueError("agent overrides must name codex, claude-code, or pi")
    out.mkdir(parents=True, exist_ok=False)
    inputs = out / "inputs"
    inputs.mkdir()
    shutil.copy2(wheel, inputs / wheel.name)
    (inputs / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in CASES))
    subprocess.run(["bash", str(ROOT / "avp/scripts/build-skill.sh"), str(inputs)], check=True)
    with zipfile.ZipFile(inputs / "avp.skill") as bundle:
        skill = {n.removeprefix("avp/"): bundle.read(n).decode() for n in bundle.namelist()}
    materials = {
        "repo": {},
        "prompt": {"system_prompt": (HERE / "PROMPT.md").read_text()},
        "cli-docs": {"system_prompt": (ROOT / "avp-cli/README.md").read_text()},
        "skill": {"skills": [{"id": "avp", "files": skill}]},
        "skill-invoked": {
            "skills": [{"id": "avp", "files": skill}],
            "system_prompt": "Use the AVP skill to complete the task.",
        },
    }
    task = (HERE / "task.md").read_text().replace("CLI_WHEEL", wheel.name)
    batch = hashlib.sha256(str(out.resolve()).encode()).hexdigest()[:8]
    trials = []
    for agent, model in models.items():
        for strategy, material in materials.items():
            cid = f"onboard-{batch}-{agent}-{strategy}"
            commission = Commission.model_validate(
                {
                    "schema_version": "0.1",
                    "run_id": cid,
                    "model": model,
                    "prompt": "{input}",
                    **material,
                }
            )
            write_json(
                out / "commissions" / f"{cid}.json",
                commission.model_dump(mode="json", exclude_none=True),
            )
            for repeat in range(repetitions):
                tid = f"{cid}-{repeat + 1}"
                config = {
                    "name": tid,
                    "agents": [agents[agent]],
                    "commissions": [cid],
                    "dataset": {
                        "source": "inline",
                        "items": [
                            {
                                "id": "setup-and-evaluate",
                                "prompt": task.replace("MODEL_SLUG", model),
                                "expected": "DONE",
                            }
                        ],
                    },
                    "scorer": {"name": "exact-match"},
                }
                write_json(out / "evals" / f"{tid}.json", config)
                trials.append(
                    {
                        "id": tid,
                        "agent": agent,
                        "model": model,
                        "strategy": strategy,
                        "repeat": repeat + 1,
                        "commission": cid,
                    }
                )
    # Inputs never include the skill or docs for the control arm. All agents
    # can independently retrieve the public repository using their tools.
    files = {
        f"inputs/{p.name}": {"from": str(p.resolve())}
        for p in inputs.iterdir()
        if p.name != "avp.skill"
    }
    write_json(
        out / "environment.json",
        {
            "packages": {"apt": ["git", "curl"], "pip": ["uv"]},
            "files": files,
            # The outer container supplies confinement; nested bwrap requires
            # user namespaces that OpenSandbox does not expose.
            "setup": [
                "printf '%s\\n' 'sandbox_mode = \"danger-full-access\"' > \"$CODEX_HOME/config.toml\""
            ],
            "net": [
                "api.github.com",
                "release-assets.githubusercontent.com",
                "nodejs.org",
                "registry.npmjs.org",
                "*.npmjs.org",
                "downloads.astral.sh",
            ],
        },
    )
    random.Random(seed).shuffle(trials)
    plan = {
        "version": 1,
        "seed": seed,
        "repetitions": repetitions,
        "agent_locators": agents,
        "cli_wheel_sha256": sha256(wheel),
        "git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff"], cwd=ROOT)
        ).hexdigest(),
        "inputs": {p.name: sha256(p) for p in inputs.iterdir()},
        "artifacts": {str(p.relative_to(out)): sha256(p) for p in sorted(out.rglob("*.json"))},
        "harness": {p.name: sha256(p) for p in sorted(HERE.glob("*.py"))},
        "trials": trials,
    }
    write_json(out / "plan.json", plan)
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        metavar="AGENT=ORIGIN/MODEL",
        help="Override a selected agent's model; repeat per agent",
    )
    parser.add_argument(
        "--agent",
        action="append",
        default=[],
        metavar="AGENT=LOCATOR",
        help="Use an installed alias or manifest for an agent; repeat per agent",
    )
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    try:
        models = dict(value.split("=", 1) for value in args.model)
    except ValueError:
        parser.error("--model must be AGENT=ORIGIN/MODEL")
    try:
        agents = dict(value.split("=", 1) for value in args.agent)
    except ValueError:
        parser.error("--agent must be AGENT=LOCATOR")
    plan = prepare(
        args.out.resolve(),
        args.wheel.resolve(),
        repetitions=args.repetitions,
        seed=args.seed,
        models=models,
        agents=agents,
    )
    print(f"Prepared {len(plan['trials'])} trials in {args.out}; no model calls made.")
