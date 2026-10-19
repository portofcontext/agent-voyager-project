"""Viewer-link payload shaping: single-agent stays flat, multi-agent folds into one.

Plus the trajectory -> RunEvent projection seam: the viz events MUST carry the
real AVP wire `type` and wire field names, not a re-vocabulary.
"""

from __future__ import annotations

from avp.content import TextBlock, ToolResultBlock
from avp.envelope import ZERO_SPAN_ID, new_span_id, new_trace_id
from avp.trajectory import (
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    AssistantMessageData,
    AssistantMessageEvent,
    StopReason,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    Usage,
)
from avp_cli import viz


def _payload(agent: str) -> dict:
    return {
        "eval_version": "v1",
        "snapshot_at": "2026-05-28T00:00:00Z",
        "agent": agent,
        "by_commission": {"baseline": []},
        "commissions": {"baseline": {}},
    }


def test_run_events_carry_the_real_wire_vocabulary() -> None:
    """The projection mirrors the wire: real `avp.*` types, wire field names.

    Guards against re-growing a bespoke display vocabulary (the removed
    `model_turn_ended` event, the `tokens_in`/`tokens_out` aliases).
    """
    trace, agent_span, turn_span, tool_span = (
        new_trace_id(),
        new_span_id(),
        new_span_id(),
        new_span_id(),
    )

    def span(span_id: str, parent: str) -> dict:
        return {"trace_id": trace, "span_id": span_id, "parent_span_id": parent}

    events = [
        AgentStartedEvent(subject="r", data=AgentStartedData(**span(agent_span, ZERO_SPAN_ID))),
        AssistantMessageEvent(
            subject="r",
            data=AssistantMessageData(
                **span(turn_span, agent_span),
                step=1,
                duration_ms=10,
                content=[TextBlock(text="hi")],
                usage=Usage(input_tokens=10, output_tokens=5),
                cost_usd=0.001,
                response_model="claude",
            ),
        ),
        ToolInvokedEvent(
            subject="r",
            data=ToolInvokedData(
                **span(tool_span, turn_span),
                step=1,
                tool_call_id="c1",
                tool_name="bash",
                tool_input={"x": 1},
                tool_dispatch_target="local",
            ),
        ),
        ToolReturnedEvent(
            subject="r",
            data=ToolReturnedData(
                **span(new_span_id(), tool_span),
                step=1,
                tool_call_id="c1",
                tool_name="bash",
                duration_ms=1,
                tool_result=ToolResultBlock(tool_use_id="c1", content="ok"),
            ),
        ),
        AgentStoppedEvent(
            subject="r",
            data=AgentStoppedData(**span(new_span_id(), agent_span), reason=StopReason.converged),
        ),
    ]
    run = viz.trajectory_to_run(events, run_id="r")
    by_type = {e["type"]: e for e in run["events"]}

    # Real wire types, verbatim, in order.
    assert [e["type"] for e in run["events"]] == [
        "avp.agent_started",
        "avp.assistant_message",
        "avp.tool_invoked",
        "avp.tool_returned",
        "avp.agent_stopped",
    ]
    # No re-vocabulary survives anywhere in the projection.
    blob = str(run["events"])
    for banned in ("model_turn_ended", "tokens_in", "tokens_out"):
        assert banned not in blob

    # Wire field names, not aliases.
    am = by_type["avp.assistant_message"]
    assert am["input_tokens"] == 10 and am["output_tokens"] == 5
    assert am["response_model"] == "claude"
    assert by_type["avp.tool_invoked"]["tool_name"] == "bash"
    assert by_type["avp.tool_invoked"]["tool_dispatch_target"] == "local"
    assert by_type["avp.agent_stopped"]["reason"] == "converged"


def test_combine_single_agent_stays_flat() -> None:
    p = _payload("goose")
    assert viz.combine_payloads([p]) is p  # no wrapper for the common case


def test_combine_multi_agent_wraps_into_agents() -> None:
    combined = viz.combine_payloads([_payload("goose"), _payload("claude-code")])
    assert set(combined) == {"eval_version", "snapshot_at", "agents"}
    assert [a["agent"] for a in combined["agents"]] == ["goose", "claude-code"]
    # each agent keeps its own by_commission slice
    assert all("by_commission" in a for a in combined["agents"])


class _Site:
    """A stand-in for agentvoyagerproject.com's share API: decodes each upload
    the way the site does (base64url, gunzip, JSON) and honors delete tokens."""

    def __init__(self) -> None:
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.shares: dict[str, dict] = {}
        shares = self.shares

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def _send(self, status: int, body: dict | None = None) -> None:
                data = json.dumps(body).encode() if body is not None else b""
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:
                import base64
                import gzip

                z = json.loads(self.rfile.read(int(self.headers["content-length"])))["z"]
                payload = json.loads(gzip.decompress(base64.urlsafe_b64decode(z)))
                share_id = f"id{len(shares):08d}"
                shares[share_id] = {"payload": payload, "token": f"tok-{share_id}"}
                host = f"http://{self.headers['host']}"
                self._send(
                    200,
                    {
                        "id": share_id,
                        "url": f"{host}/r/{share_id}",
                        "delete_token": f"tok-{share_id}",
                        "expires_at": "2026-11-18T00:00:00.000Z",
                    },
                )

            def do_DELETE(self) -> None:
                share_id = self.path.rsplit("/", 1)[-1]
                token = self.headers.get("authorization", "").removeprefix("Bearer ")
                if share_id in shares and shares[share_id]["token"] == token:
                    del shares[share_id]
                    self._send(204)
                else:
                    self._send(404, {"error": "not found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"


def test_share_uploads_a_run_the_site_decodes_and_unshare_takes_it_down(tmp_path) -> None:
    import json

    from avp_cli import cli

    site = _Site()
    out = tmp_path / "bold-horizon"
    out.mkdir()
    for agent in ("goose", "claude-code"):
        (out / f"trajectories.{agent}.json").write_text(json.dumps(_payload(agent)))
    (out / "run.json").write_text(json.dumps({"eval_config": {"name": "agent-runoff"}}))

    # Uploading needs consent: without a TTY, --yes is required.
    assert cli.main(["eval", "share", str(out), "--site", site.url]) == 1
    assert site.shares == {}

    assert cli.main(["eval", "share", str(out), "--yes", "--site", site.url]) == 0
    [(share_id, stored)] = site.shares.items()
    combined = viz.combine_payloads(
        [json.loads((out / f"trajectories.{a}.json").read_text()) for a in ("claude-code", "goose")]
    )
    assert stored["payload"] == {**combined, "name": "agent-runoff"}
    record = json.loads((out / "share.json").read_text())
    assert record["id"] == share_id and record["delete_token"] == f"tok-{share_id}"

    assert cli.main(["eval", "unshare", str(out)]) == 0
    assert site.shares == {}
    assert not (out / "share.json").exists()
    site.server.shutdown()


def test_share_reports_a_refused_upload() -> None:
    import pytest

    with pytest.raises(viz.ShareError, match="could not reach"):
        viz.share({"eval_version": "0.1"}, site="http://127.0.0.1:9")
