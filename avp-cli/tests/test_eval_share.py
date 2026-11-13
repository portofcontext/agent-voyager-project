"""What `avp eval share` uploads, and its calls to the site, without the site."""

import base64
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import atif

from avp.artifacts import ArtifactFile, write_artifacts
from avp_cli import paths
from avp_cli.console import Failed
from avp_cli.eval import share
from avp_cli.eval.results import EvalResults, RunResult
from avp_cli.eval.scoring import Score, Totals

SECRET = "sk-never-uploaded"
MODEL = {"provider": "openai", "id": "gpt-test"}
PROMPT = "What is the capital of France?"
LONG = "x" * 5000


def trajectory(run_id: str) -> str:
    doc = atif(run_id=run_id)
    doc["agent"] = {
        "name": "avp-test",
        "version": "1.2.3",
        "model_name": "gpt-test",
        "extra": {"avp": {"provider": "openai"}},
        "tool_definitions": [
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "description": "Read a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string", "description": "The file."}},
                        "required": ["path"],
                    },
                },
            }
        ],
    }
    metrics = {"prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.01}
    doc["steps"] = [
        {"step_id": 1, "source": "user", "message": PROMPT},
        {
            "step_id": 2,
            "source": "agent",
            "message": "",
            "metrics": metrics,
            "extra": {"avp": {"duration_ms": 7}},
            "tool_calls": [
                {
                    "tool_call_id": "call-1",
                    "function_name": "read",
                    "arguments": {"path": "/a"},
                    "extra": {"avp": {"started_at": "2026-01-01T00:00:00Z"}},
                }
            ],
            "observation": {
                "results": [
                    {
                        "source_call_id": "call-1",
                        "content": LONG,
                        "extra": {"avp": {"finished_at": "2026-01-01T00:00:00.003Z"}},
                    }
                ]
            },
        },
        {
            "step_id": 3,
            "source": "agent",
            "message": "Paris",
            "metrics": metrics,
            "extra": {"avp": {"duration_ms": 9}},
        },
    ]
    return json.dumps(doc)


def eval_directory(tmp_path: Path, agents: list[str]) -> tuple[Path, EvalResults]:
    """An eval run's directory as `avp eval run` leaves it, one run per agent."""
    directory = tmp_path / "20260101T000000Z-capitals"
    file = {
        "eval_version": "0.1",
        "name": "capitals",
        "commission": {"avp_version": "0.1", "model": MODEL, "prompt": "{item.question}"},
        "dataset": [{"id": "france", "question": PROMPT, "answer": "Paris"}],
        "scorer": {"name": "match", "expected": "{item.answer}"},
    }
    directory.mkdir()
    (directory / paths.EVAL).write_text(json.dumps(file))
    runs = []
    for agent in agents:
        run_id = f"id-inline-1-{agent}-france"
        run = directory / paths.EVAL_RUNS / run_id
        run.mkdir(parents=True)
        commission = {
            "avp_version": "0.1",
            "run_id": run_id,
            "model": MODEL | {"base_url": "http://mock", "credential": {"env": "KEY"}},
            "prompt": PROMPT,
            "mcp_servers": [
                {"id": "docs", "type": "http", "url": "https://mcp", "headers": {"x-key": SECRET}}
            ],
        }
        (run / paths.COMMISSION).write_text(json.dumps(commission))
        (run / paths.TRAJECTORY).write_text(trajectory(run_id))
        runs.append(
            RunResult(
                run_id=run_id,
                commission="inline-1",
                agent=agent,
                item="france",
                exit_code=0,
                reason="converged",
                score=Score(value=1, passed=True),
                directory=f"{paths.EVAL_RUNS}/{run_id}",
                model="openai/gpt-test",
                seconds=1.5,
                totals=Totals(turns=2, input_tokens=20, output_tokens=10, cost_usd=0.02),
            )
        )
    results = EvalResults(
        id=directory.name, name="capitals", started=datetime(2026, 1, 1, tzinfo=UTC), runs=runs
    )
    return directory, results


def test_a_run_is_what_the_sites_viewer_reads(tmp_path: Path) -> None:
    payload = share.payload(*eval_directory(tmp_path, ["one"]))
    assert payload["name"] == "capitals"
    assert payload["agent"] == "one"
    [run] = payload["by_commission"]["inline-1"]
    assert run | {"events": [], "vessel": {}, "orders": {}} == {
        "row_id": "france",
        "run_id": "id-inline-1-one-france",
        "passed": True,
        "score": 1,
        "stop_reason": "converged",
        "total_cost_usd": 0.02,
        "total_turns": 2,
        "total_tokens": 30,
        "elapsed_s": 1.5,
        "question": PROMPT,
        "expected": "Paris",
        "events": [],
        "vessel": {},
        "orders": {},
    }
    assert run["orders"] == {"task": PROMPT}
    assert run["vessel"] == {
        "agent": "avp-test",
        "version": "1.2.3",
        "model": "openai/gpt-test",
        "tools": [
            {
                "name": "read",
                "description": "Read a file.",
                "params": [
                    {"name": "path", "required": True, "type": "string", "description": "The file."}
                ],
            }
        ],
    }
    events = run["events"]
    assert [e["type"] for e in events] == [
        "avp.agent_started",
        "avp.assistant_message",
        "avp.tool_invoked",
        "avp.tool_returned",
        "avp.assistant_message",
        "avp.agent_stopped",
    ]
    assert [e["seq"] for e in events] == list(range(6))
    assert events[1]["input_tokens"] == 10 and events[1]["cost_usd"] == 0.01
    assert events[2]["call_id"] == events[3]["call_id"] == "call-1"
    assert events[1]["response_model"] == "gpt-test"
    assert events[3]["duration_ms"] == 3
    assert events[3]["result_chars"] == len(LONG)
    assert events[3]["result"].endswith(f"(+{len(LONG) - share.TEXT} chars)")
    assert events[4]["text"] == "Paris"
    assert events[5] == {
        "seq": 5,
        "type": "avp.agent_stopped",
        "reason": "converged",
        "output": "Paris",
    }


def test_no_credential_header_or_endpoint_is_uploaded(tmp_path: Path) -> None:
    payload = share.payload(*eval_directory(tmp_path, ["one"]))
    text = json.dumps(payload)
    assert SECRET not in text
    assert "http://mock" not in text
    assert "credential" not in text
    assert payload["commissions"]["inline-1"] == {
        "model": "openai/gpt-test",
        "prompt": PROMPT,
        "mcp_servers": [{"id": "docs", "type": "http", "url": "https://mcp"}],
    }


def test_several_agents_are_one_slice_each(tmp_path: Path) -> None:
    payload = share.payload(*eval_directory(tmp_path, ["one", "two"]))
    assert [s["agent"] for s in payload["agents"]] == ["one", "two"]
    assert "by_commission" not in payload


def test_a_run_that_never_started_is_shared_without_events(tmp_path: Path) -> None:
    directory, results = eval_directory(tmp_path, ["one"])
    (directory / results.runs[0].directory / paths.TRAJECTORY).unlink()
    results.runs[0].score = Score(value=0, passed=False, reasons=["the sandbox didn't start"])
    [run] = share.payload(directory, results)["by_commission"]["inline-1"]
    assert run["events"] == []
    assert run["passed"] is False
    assert run["total_cost_usd"] is None
    assert run["verdict"] == "the sandbox didn't start"


def test_share_uploads_keeps_the_link_and_unshare_takes_it_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, results = eval_directory(tmp_path, ["one"])
    calls: list[tuple[str, str, Any, dict[str, str]]] = []

    def request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        calls.append((method, url, kwargs.get("json"), kwargs["headers"]))
        answer = {
            "id": "abcdefghij",
            "url": "https://site.test/eval/abcdefghij",
            "delete_token": "token",
            "expires_at": "2026-02-01T00:00:00Z",
        }
        return httpx.Response(200 if method == "POST" else 204, json=answer)

    monkeypatch.setattr(httpx, "request", request)
    shared = share.share(directory, results, "https://site.test/")
    assert shared.url == "https://site.test/eval/abcdefghij"
    method, url, body, _ = calls[0]
    assert (method, url) == ("POST", "https://site.test/api/runs")
    uploaded = json.loads(gzip.decompress(base64.urlsafe_b64decode(body["z"])))
    assert uploaded["by_commission"]["inline-1"][0]["row_id"] == "france"
    assert share.shared(directory) == shared
    share.unshare(directory)
    method, url, _, headers = calls[1]
    assert (method, url) == ("DELETE", "https://site.test/api/runs/abcdefghij")
    assert headers["authorization"] == "Bearer token"
    assert share.shared(directory) is None
    with pytest.raises(Failed, match="isn't shared"):
        share.unshare(directory)


def test_a_refusal_says_why(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory, results = eval_directory(tmp_path, ["one"])
    monkeypatch.setattr(
        httpx, "request", lambda *a, **k: httpx.Response(413, json={"error": "run too large"})
    )
    with pytest.raises(Failed, match="run too large"):
        share.share(directory, results, "https://site.test")
    assert share.shared(directory) is None


def test_effective_configuration_is_read_from_verified_artifacts(tmp_path: Path) -> None:
    directory, results = eval_directory(tmp_path, ["one"])
    run = results.runs[0]
    run_directory = directory / run.directory
    effective = {
        "skills": [
            {
                "name": "research",
                "description": "Research.",
                "source": "file:inputs/skills/research",
            }
        ],
        "mcp_servers": [{"id": "docs", "status": "connected"}],
    }
    write_artifacts(
        run_directory,
        run.run_id,
        {
            "inputs/effective-agent.json": ArtifactFile(json.dumps(effective).encode(), "input"),
        },
    )
    [shown] = share.payload(directory, results)["by_commission"]["inline-1"]
    assert shown["vessel"]["skills"] == effective["skills"]
    assert shown["vessel"]["mcp_servers"] == effective["mcp_servers"]
    (run_directory / "inputs/effective-agent.json").write_text("{}")
    with pytest.raises(Failed, match="hash mismatch"):
        share.payload(directory, results)
