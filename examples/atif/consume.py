"""Use an ordinary ATIF file with Harbor's viewer and training trace extractor.

Run with the pinned Harbor environment described in README.md. No AVP dependency.
"""

import argparse
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from harbor.models.job.config import JobConfig
from harbor.models.job.result import JobResult, JobStats
from harbor.models.trajectories import Trajectory
from harbor.models.trial.config import AgentConfig, TaskConfig, TrialConfig
from harbor.models.trial.result import AgentInfo, TrialResult
from harbor.utils.traces_utils import extract_conversations_from_trajectory


def prepare(source: Path, destination: Path) -> Path:
    """Create Harbor job metadata and copy the original document byte for byte."""
    trajectory = Trajectory.model_validate_json(source.read_text())
    destination.mkdir(parents=True, exist_ok=False)
    job = destination / "avp-import"
    trial = job / "run"
    agent_dir = trial / "agent"
    agent_dir.mkdir(parents=True)
    shutil.copyfile(source, agent_dir / "trajectory.json")

    def assets(value):
        if isinstance(value, dict):
            if value.get("type") == "image" and "path" in value.get("source", {}):
                relative = Path(value["source"]["path"])
                asset = (source.parent / relative).resolve()
                if relative.is_absolute() or not asset.is_relative_to(source.parent.resolve()):
                    raise ValueError(f"Media path escapes the trajectory directory: {relative}")
                target = agent_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(asset, target)
            for child in value.values():
                assets(child)
        elif isinstance(value, list):
            for child in value:
                assets(child)

    assets(trajectory.to_json_dict())
    manifest_path = source.parent / "artifacts.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_bytes())
        if manifest["avp_version"] != "0.1" or manifest["run_id"] != trajectory.session_id:
            raise ValueError("Artifact manifest version or run identity does not match")
        seen = set()
        for entry in manifest["artifacts"]:
            name = entry["path"]
            if (
                name in seen
                or name in {"trajectory.json", "artifacts.json"}
                or any(part in {"", ".", ".."} for part in name.split("/"))
                or re.search(r"[\\:\x00-\x1f]", name)
                or entry["role"] not in {"input", "output"}
            ):
                raise ValueError(f"Invalid artifact: {name}")
            seen.add(name)
            asset = (source.parent / name).resolve()
            if not asset.is_relative_to(source.parent.resolve()):
                raise ValueError(f"Artifact path escapes the run directory: {name}")
            content = asset.read_bytes()
            if hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError(f"Artifact hash mismatch: {name}")
            target = agent_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        shutil.copyfile(manifest_path, agent_dir / "artifacts.json")
    agent = AgentConfig(name=trajectory.agent.name, model_name=trajectory.agent.model_name)
    task = TaskConfig(path=source.resolve())
    config = TrialConfig(task=task, trial_name="run", agent=agent)
    (trial / "config.json").write_text(config.model_dump_json(indent=2))
    (job / "config.json").write_text(
        JobConfig(job_name=job.name, agents=[agent]).model_dump_json(indent=2)
    )
    meta = (trajectory.extra or {}).get("avp", {})
    started = meta.get("started_at") or meta.get("requested_at")
    started = (
        datetime.fromisoformat(started.replace("Z", "+00:00")) if started else datetime.now(UTC)
    )
    stopped = meta.get("stopped_at")
    finished = datetime.fromisoformat(stopped.replace("Z", "+00:00")) if stopped else None
    if meta.get("complete"):
        # The import time is only a fallback for documents without run timestamps.
        finished = finished or started
        result = TrialResult(
            task_name=source.stem,
            trial_name="run",
            trial_uri=trial.resolve().as_uri(),
            task_id={"path": str(source.resolve())},
            task_checksum=hashlib.sha256(source.read_bytes()).hexdigest(),
            config=config,
            agent_info=AgentInfo(name=trajectory.agent.name, version=trajectory.agent.version),
            started_at=started,
            finished_at=finished,
        )
        (trial / "result.json").write_text(result.model_dump_json(indent=2))
    result = JobResult(
        id=uuid4(),
        started_at=started,
        finished_at=finished,
        n_total_trials=1,
        stats=JobStats(n_completed_trials=int(bool(meta.get("complete")))),
    )
    (job / "result.json").write_text(result.model_dump_json(indent=2))
    return agent_dir / "trajectory.json"


def conversations(source: Path) -> list[dict]:
    trajectory = Trajectory.model_validate_json(source.read_text())
    return extract_conversations_from_trajectory(
        source,
        {
            "agent_name": trajectory.agent.name,
            "model_name": trajectory.agent.model_name or "unknown",
            "model_provider": (trajectory.agent.extra or {})
            .get("avp", {})
            .get("provider", "unknown"),
            "start_time": (trajectory.extra or {}).get("avp", {}).get("started_at", ""),
            "run_id": trajectory.session_id,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trajectory", type=Path)
    parser.add_argument("--jobs", type=Path, help="Create a new Harbor jobs directory for viewing")
    parser.add_argument("--conversations", type=Path, help="Write Harbor's text training examples")
    args = parser.parse_args()
    if args.jobs:
        prepare(args.trajectory, args.jobs)
        print(f"harbor view {args.jobs} --jobs")
    if args.conversations:
        args.conversations.write_text(json.dumps(conversations(args.trajectory), indent=2) + "\n")
