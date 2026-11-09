"""Exercise unmodified upstream consumers. Run in the example's Harbor environment."""

import asyncio
import importlib.util
import json
import sys
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
    source = directory / "trajectory.json"
    sys.path.insert(0, str(ROOT / "avp-sdk/python/src"))
    from avp.commission import ModelRef
    from avp.descriptor import AgentDescriptor, Tool
    from avp.recorder import Recorder, UsageReport
    from avp.reports import RunContext, TextBlock, ToolUseBlock

    async def record():
        async def sink(snapshot):
            snapshot.write(source)
            # Validate each live snapshot using upstream's separately installed model.
            Trajectory.model_validate_json(source.read_text())

        recorder = Recorder(sink, run_id="ecosystem")
        await recorder.begin(
            None, AgentDescriptor(avp_version="0.1", agent_name="avp-example", agent_version="1")
        )
        await recorder.start(
            RunContext(
                prompt="What is 20 + 22?",
                model=ModelRef(provider="test", id="fixture"),
                tools=[Tool(name="add", inputSchema={"type": "object"})],
            )
        )
        await recorder.response(
            [ToolUseBlock(type="tool_use", id="call-1", name="add", input={"a": 20, "b": 22})],
            usage=UsageReport(input_tokens=30, output_tokens=12),
        )
        await recorder.tool_returned("call-1", "42")
        await recorder.response(
            [TextBlock(type="text", text="The answer is 42.")],
            usage=UsageReport(input_tokens=45, output_tokens=6),
        )
        await recorder.stop("converged", {"answer": 42})

    asyncio.run(record())
    document = json.loads(source.read_text())
    Trajectory.model_validate_json(source.read_text())
    rows = example.conversations(source)
    assert len(rows) == sum(s["source"] == "agent" for s in document["steps"])
    assert "42" in json.dumps(rows[-1])
    assert "add" in json.dumps(rows[-1])
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
