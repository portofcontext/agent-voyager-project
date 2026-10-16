"""Seam tests: the adapter driving the SDK's bundled Claude CLI against a local
Anthropic Messages endpoint, checking what the model is offered against the
trajectory. No network, no credentials."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from avp.commission import Commission
from avp.trajectory import Event
from avp_claude_agent_sdk.conformance import run

_AGENT = "avp-claude-agent-sdk"


def _sse(text: str, tool: dict[str, Any] | None = None, output_tokens: int = 7) -> bytes:
    """One streamed response: `text`, then `tool` (a `tool_use` block) if given.
    `message_start` reports 1 output token; `message_delta` the real count."""
    blocks: list[dict[str, Any]] = [
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
    ]
    if tool is not None:
        start = {"type": "tool_use", "id": tool["id"], "name": tool["name"], "input": {}}
        blocks += [
            {"type": "content_block_start", "index": 1, "content_block": start},
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool["input"])},
            },
            {"type": "content_block_stop", "index": 1},
        ]
    events = [
        {
            "type": "message_start",
            "message": {
                "id": f"msg_{output_tokens}",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5",
                "content": [],
                "stop_reason": None,
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        },
        *blocks,
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use" if tool else "end_turn"},
            "usage": {"output_tokens": output_tokens},
        },
        {"type": "message_stop"},
    ]
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


class _Model:
    """Answers streamed Messages requests with the `script`ed responses, then
    `DONE`, recording the bodies (`posted` also keeps the requests it refuses)."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.posted: list[dict[str, Any]] = []
        self.script: list[bytes] = []
        requests, posted, script = self.requests, self.posted, self.script

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
                if self.path.split("?")[0].endswith("/count_tokens"):
                    # Free on the real API, so not a model request.
                    self._json({"input_tokens": 10})
                    return
                posted.append(body)
                if not body.get("stream"):
                    self.send_response(404)
                    self.end_headers()
                    return
                requests.append(body)
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                self.wfile.write(script.pop(0) if script else _sse("DONE"))

            def _json(self, payload: dict[str, Any]) -> None:
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def tools(self) -> dict[str, dict[str, Any]]:
        """The tools of the run's main-session request (the one with our prompt)."""
        main = [
            r
            for r in self.requests
            if "tools" in r and "do the thing" in json.dumps(r.get("messages"))
        ]
        return {t["name"]: t for t in main[-1]["tools"]}


@pytest.fixture
def model(tmp_path, monkeypatch) -> Iterator[_Model]:
    served = _Model()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", served.url)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)
    yield served
    served.server.shutdown()


def _run(**fields: Any) -> list[dict[str, Any]]:
    commission = Commission(
        schema_version="0.1",
        run_id="claude-seam",
        model="anthropic/claude-haiku-4-5",
        prompt="do the thing",
        **fields,
    )
    events: list[Event] = []

    async def sink(event: Event) -> None:
        events.append(event)

    asyncio.run(run(commission, sink))
    return [e.model_dump(by_alias=True, exclude_none=True, mode="json") for e in events]


def _started(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(e for e in events if e["type"] == "avp.agent_started")["data"]


def test_withheld_subagents_leave_the_agent_tool(model: _Model) -> None:
    events = _run(enabled_builtin_subagents={_AGENT: ["general-purpose"]})
    agent = model.tools()["Agent"]["description"]
    assert "- general-purpose:" in agent
    assert "- Explore:" not in agent and "- Plan:" not in agent
    assert [s["name"] for s in _started(events)["avp.subagents"]] == ["general-purpose"]
    assert events[-1]["data"]["avp.reason"] == "converged"


def test_no_subagents_removes_the_agent_tool(model: _Model) -> None:
    events = _run(enabled_builtin_subagents={_AGENT: []})
    assert "Agent" not in model.tools()
    started = _started(events)
    assert started.get("avp.subagents", []) == []
    assert "Agent" not in [t["name"] for t in started["avp.tools"]]


def test_no_built_in_skills_hides_them_from_the_model(model: _Model) -> None:
    events = _run(enabled_builtin_skills={_AGENT: []})
    assert "update-config" not in json.dumps(model.requests[-1])
    assert _started(events).get("avp.skills", []) == []


def test_the_probe_reaches_no_model(model: _Model) -> None:
    """The probe session's own prompt never reaches the endpoint: every request
    the model sees belongs to the run, so the trajectory accounts for all spend."""
    events = _run()
    assert model.requests, "the run itself calls the model"
    assert not [r for r in model.requests if "probing claude" in json.dumps(r)]
    turns = [e for e in events if e["type"] == "avp.assistant_message"]
    assert len(turns) == 1


def test_every_model_request_is_a_recorded_turn(model: _Model) -> None:
    """No side request (a session title) spends tokens the trajectory omits,
    and each turn carries its response's final usage: `message_start` says 1
    output token, `message_delta` the real 7."""
    events = _run()
    turns = [e for e in events if e["type"] == "avp.assistant_message"]
    assert len(model.posted) == len(turns), [json.dumps(r["messages"])[:80] for r in model.posted]
    assert [t["data"]["avp.usage"]["output_tokens"] for t in turns] == [7]
    assert [t["data"]["avp.usage"]["input_tokens"] for t in turns] == [10]


def test_a_tool_turn_carries_its_final_usage(model: _Model) -> None:
    """The final usage of a response that calls a tool lands on its own turn,
    not the turn after the tool result."""
    bash = {"id": "toolu_1", "name": "Bash", "input": {"command": "echo hi", "description": "hi"}}
    model.script.append(_sse("running", tool=bash, output_tokens=30))
    events = _run(enabled_builtin_tools={_AGENT: ["Bash"]})
    turns = [e["data"] for e in events if e["type"] == "avp.assistant_message"]
    assert [t["avp.usage"]["output_tokens"] for t in turns] == [30, 7]
    assert any(e["type"] == "avp.tool_returned" for e in events)
    assert events[-1]["data"]["avp.reason"] == "converged"
