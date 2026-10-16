"""The metering proxy: usage parsing per provider format, forwarding, and
reconciling the bill with a trajectory."""

from __future__ import annotations

import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from avp_conformance._meter import Billed, Meter, reconcile, usage_of


def _sse(*payloads: dict) -> bytes:
    return "".join(f"data: {json.dumps(p)}\n\n" for p in payloads).encode()


ANTHROPIC_SSE = _sse(
    {
        "type": "message_start",
        "message": {
            "usage": {
                "input_tokens": 10,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 5,
                "output_tokens": 1,
            }
        },
    },
    {"type": "content_block_delta", "delta": {"text": "hi"}},
    {"type": "message_delta", "usage": {"output_tokens": 42}},
    {"type": "message_stop"},
)


@pytest.mark.parametrize(
    ("body", "content_type", "expected"),
    [
        (ANTHROPIC_SSE, "text/event-stream", (115, 42)),
        (
            json.dumps({"type": "message", "usage": {"input_tokens": 7, "output_tokens": 3}}),
            "application/json",
            (7, 3),
        ),
        (
            _sse(
                {"type": "response.created", "response": {}},
                {
                    "type": "response.completed",
                    "response": {"usage": {"input_tokens": 50, "output_tokens": 9}},
                },
            ),
            "text/event-stream",
            (50, 9),
        ),
        (
            json.dumps(
                {
                    "object": "response",
                    "status": "completed",
                    "usage": {"input_tokens": 4, "output_tokens": 2},
                }
            ),
            "application/json",
            (4, 2),
        ),
        (
            _sse(
                {"object": "chat.completion.chunk", "choices": [{"delta": {"content": "x"}}]},
                {
                    "object": "chat.completion.chunk",
                    "choices": [],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 6},
                },
            )
            + b"data: [DONE]\n\n",
            "text/event-stream",
            (30, 6),
        ),
        (
            _sse(
                {"usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 1}},
                {
                    "usageMetadata": {
                        "promptTokenCount": 20,
                        "toolUsePromptTokenCount": 3,
                        "candidatesTokenCount": 8,
                        "thoughtsTokenCount": 4,
                    }
                },
            ),
            "text/event-stream",
            (23, 12),
        ),
        (
            json.dumps([{"usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1}}]),
            "application/json",
            (2, 1),
        ),
        (json.dumps({"input_tokens": 99}), "application/json", None),
        (json.dumps({"data": [{"id": "model"}]}), "application/json", None),
    ],
    ids=[
        "anthropic-sse",
        "anthropic-json",
        "responses-sse",
        "responses-json",
        "chat-sse",
        "gemini-sse",
        "gemini-array",
        "token-count",
        "model-list",
    ],
)
def test_usage_of_reads_each_provider_format(body, content_type, expected) -> None:
    raw = body if isinstance(body, bytes) else body.encode()
    assert usage_of(raw, content_type) == expected


class _Upstream:
    """Serves ANTHROPIC_SSE on POST (or `status`), recording request bodies,
    and closes the stream `linger` seconds after its last event."""

    def __init__(self, status: int = 200, linger: float = 0.0) -> None:
        self.bodies: list[bytes] = []
        bodies = self.bodies

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_POST(self) -> None:
                bodies.append(self.rfile.read(int(self.headers["content-length"])))
                self.send_response(status)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                self.wfile.write(ANTHROPIC_SSE)
                self.wfile.flush()
                time.sleep(linger)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"


def _post(url: str, body: bytes, chunked: bool = False) -> bytes:
    split = url.removeprefix("http://")
    conn = http.client.HTTPConnection(split.split("/")[0])
    path = "/" + split.split("/", 1)[1] if "/" in split else "/v1/messages"
    if chunked:
        conn.request("POST", path, body=iter([body[:3], body[3:]]), encode_chunked=True)
    else:
        conn.request("POST", path, body=body)
    return conn.getresponse().read()


def test_the_meter_forwards_and_records_completed_responses() -> None:
    upstream = _Upstream()
    with Meter({"anthropic": upstream.url}) as meter:
        assert meter.env()["ANTHROPIC_BASE_URL"] == meter.url("anthropic")
        assert _post(meter.url("anthropic"), b'{"a":1}') == ANTHROPIC_SSE
        _post(meter.url("anthropic"), b'{"b":2}', chunked=True)
        assert upstream.bodies == [b'{"a":1}', b'{"b":2}']
        assert meter.take() == [Billed("/v1/messages", 115, 42)] * 2
        assert meter.take() == []
    upstream.server.shutdown()


def test_take_waits_for_a_stream_the_provider_closes_late() -> None:
    # The agent reads the final event and exits; the provider closes after.
    upstream = _Upstream(linger=0.5)
    with Meter({"anthropic": upstream.url}) as meter:
        conn = http.client.HTTPConnection(meter.url("anthropic").removeprefix("http://"))
        conn.request("POST", "/v1/messages", body=b"{}")
        assert conn.getresponse().read(len(ANTHROPIC_SSE)) == ANTHROPIC_SSE
        conn.close()
        assert meter.take() == [Billed("/v1/messages", 115, 42)]
    upstream.server.shutdown()


def test_a_failed_response_is_not_billed() -> None:
    upstream = _Upstream(status=429)
    with Meter({"anthropic": upstream.url}) as meter:
        _post(meter.url("anthropic"), b"{}")
        assert meter.take() == []
    upstream.server.shutdown()


def _turn(inp: int, out: int) -> dict:
    return {
        "type": "avp.assistant_message",
        "data": {"avp.usage": {"input_tokens": inp, "output_tokens": out}},
    }


def test_reconcile_accepts_a_fully_recorded_bill() -> None:
    billed = [Billed("/v1/messages", 100, 10), Billed("/v1/messages", 50, 5)]
    child = {
        "type": "avp.subagent_returned",
        "data": {"avp.subagent.usage": {"tokens_input": 50, "tokens_output": 5}},
    }
    assert reconcile(billed, [_turn(100, 10), child]) == []


def test_reconcile_flags_an_unrecorded_call() -> None:
    billed = [Billed("/v1/messages", 100, 10), Billed("/v1/messages", 30, 2)]
    [reason] = reconcile(billed, [_turn(100, 10)])
    assert "130 input / 12 output" in reason and "100 / 10" in reason


def test_reconcile_compares_totals_when_a_rollup_reports_only_a_total() -> None:
    billed = [Billed("/v1/messages", 100, 10), Billed("/v1/messages", 40, 5)]
    child = {"type": "avp.subagent_returned", "data": {"avp.subagent.usage": {"total_tokens": 45}}}
    assert reconcile(billed, [_turn(100, 10), child]) == []
    assert reconcile(billed, [_turn(100, 10)]) != []


def test_reconcile_needs_at_least_the_completed_bill_when_a_response_was_cut() -> None:
    billed = [Billed("/v1/messages", 100, 10), Billed("/v1/messages", 30, 0, complete=False)]
    assert reconcile(billed, [_turn(100, 10), _turn(30, 4)]) == []
    assert reconcile(billed, [_turn(100, 10)]) == []
    [reason] = reconcile(billed, [_turn(90, 10)])
    assert "1 cut off" in reason
