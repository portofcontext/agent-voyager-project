"""Exercise unmodified upstream consumers. Run in the example's Harbor environment."""

import importlib.util
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from harbor.models.trajectories import Trajectory
from harbor.viewer.scanner import JobScanner
from harbor.viewer.server import create_app

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("atif_example", ROOT / "examples/atif/consume.py")
assert spec and spec.loader
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)

with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    fixtures = [
        json.loads(path.read_text())["trajectory"]
        for path in (ROOT / "avp-sdk/testdata/recorder").glob("*.json")
    ]
    document = next(
        doc
        for doc in fixtures
        if len([s for s in doc["steps"] if s["source"] == "agent"]) > 1
        and any(s.get("tool_calls") for s in doc["steps"])
    )
    source = directory / "trajectory.json"
    source.write_text(json.dumps(document))
    Trajectory.model_validate_json(source.read_text())
    rows = example.conversations(source)
    assert len(rows) == sum(s["source"] == "agent" for s in document["steps"])
    assert any("tool" in json.dumps(row).lower() for row in rows)
    jobs = directory / "jobs"
    copied = example.prepare(source, jobs)
    assert copied.read_bytes() == source.read_bytes()
    scanner = JobScanner(jobs)
    assert scanner.list_jobs() == ["avp-import"]
    assert scanner.list_trials("avp-import") == ["run"]
    assert scanner.get_trial_config("avp-import", "run") is not None
    assert scanner.get_trial_result("avp-import", "run") is not None
    with TestClient(create_app(jobs)) as client:
        response = client.get("/api/jobs/avp-import/trials/run/trajectory")
        assert response.status_code == 200, response.text
        assert response.json() == document
    print(
        f"Harbor: native ATIF validated; {len(rows)} training episodes; viewer served unchanged document"
    )
