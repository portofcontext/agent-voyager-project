"""The mock model in a real sandbox, reached from another: what a case's agent
sees, without an agent. Needs a container engine and pulls aimock's image."""

import json
from collections.abc import Generator

import pytest
from conftest import DESCRIPTOR
from docker.errors import DockerException
from opensandbox.sync.sandbox import SandboxSync

from avp.commission import Commission
from avp_cli.conformance import mock
from avp_cli.conformance.cases import Case
from avp_cli.console import Failed
from avp_cli.engine import client
from avp_cli.sandbox import sandboxes


def engine_answers() -> bool:
    try:
        client()
    except (Failed, DockerException):
        return False
    return True


pytestmark = [
    pytest.mark.skipif(not engine_answers(), reason="no container engine answers"),
    pytest.mark.usefixtures("avp_home"),
]

REPLY = "A scripted reply."
MCP_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "avp-test", "version": "1"},
    },
}


def case(name: str = "a-case") -> Case:
    def no_commission(context: object) -> Commission:
        raise AssertionError("not used")

    return Case(
        name=name,
        rule="trajectory.4.1",
        level="MUST",
        about="x",
        commission=no_commission,
        check=lambda run, seen: [],
        responses=({"content": REPLY},),
    )


@pytest.fixture(scope="module")
def url() -> Generator[str]:
    with mock.serving([case()], DESCRIPTOR) as server:
        yield server.url


def fetch(box: SandboxSync, url: str, prompt: str, stream: bool = False) -> sandboxes.Result:
    """Asks the way Anthropic's API is asked, and prints the status and the body."""
    body = {
        "model": "claude-haiku-4-5",
        "max_tokens": 16,
        "stream": stream,
        "messages": [{"role": "user", "content": prompt}],
    }
    script = (
        "fetch(process.argv[1],{method:'POST',signal:AbortSignal.timeout(5000),"
        "headers:{'content-type':'application/json','x-api-key':'x',"
        "'anthropic-version':'2023-06-01'},body:process.argv[2]})"
        ".then(async r=>console.log(r.status,await r.text()))"
        ".catch(e=>{console.log(e.cause?.code||e.name);process.exit(3)})"
    )
    return sandboxes.run(box, ["node", "-e", script, url, json.dumps(body)])


def host(url: str) -> str:
    return url.removeprefix("http://").rsplit(":", 1)[0]


def test_an_allowed_sandbox_gets_the_scripted_reply(url: str) -> None:
    with sandboxes.sandbox(mock.IMAGE, allowed_hosts=[host(url)]) as box:
        answer = fetch(box, f"{url}{mock.path('anthropic')}/v1/messages", case().prompt)
        assert answer.stdout.startswith("200 ")
        assert REPLY in answer.stdout

        streamed = fetch(box, f"{url}/v1/messages", case().prompt, stream=True)
        assert "event: message_start" in streamed.stdout

        missed = fetch(box, f"{url}/v1/messages", "nobody scripted this")
        assert missed.stdout.startswith("503 ")
        assert "no fixture matched" in missed.stdout


def test_a_sandbox_not_allowed_the_mock_cannot_reach_it(url: str) -> None:
    with sandboxes.sandbox(mock.IMAGE, allowed_hosts=[]) as box:
        assert fetch(box, f"{url}/v1/messages", case().prompt).exit_code == 3


def post(box: SandboxSync, url: str, body: dict) -> str:
    """The status of a JSON POST, sent with an MCP client's Accept header."""
    script = (
        "fetch(process.argv[1],{method:'POST',headers:{'content-type':'application/json',"
        "accept:'application/json, text/event-stream','x-avp-test':'kept'},"
        "body:process.argv[2]}).then(r=>console.log(r.status))"
    )
    return sandboxes.run(box, ["node", "-e", script, url, json.dumps(body)]).stdout.strip()


def test_the_journal_holds_a_cases_requests_and_each_case_has_its_mcp_server() -> None:
    with_tool = Case(
        name="with-tool",
        rule="trajectory.4.5",
        level="MUST",
        about="x",
        commission=case().commission,
        check=lambda run, seen: [],
        responses=({"content": REPLY},),
        mcp_tools=({"name": "t", "result": "r"},),
    )
    with mock.serving([with_tool, case()], DESCRIPTOR) as server:
        host_name = host(server.url)
        with sandboxes.sandbox(mock.IMAGE, allowed_hosts=[host_name]) as box:
            assert fetch(box, f"{server.url}/v1/messages", with_tool.prompt).stdout.startswith(
                "200 "
            )
            assert fetch(box, f"{server.url}/v1/messages", case().prompt).stdout.startswith("200 ")
            assert post(box, f"{server.url}/mcp/with-tool", MCP_INITIALIZE) == "200"
            assert post(box, f"{server.url}/mcp/a-case", MCP_INITIALIZE) != "200"
        [request] = server.requests(with_tool)
        assert request.body["model"] == "claude-haiku-4-5"
        assert len(server.requests(case())) == 1
        mcp = server.mcp_requests(with_tool)
        assert mcp and mcp[0].headers.get("x-avp-test") == "kept"


def test_the_mock_itself_has_no_outbound_access() -> None:
    with sandboxes.sandbox(mock.IMAGE, allowed_hosts=[]) as box:
        assert fetch(box, "https://example.com/", "x").exit_code == 3


def test_a_bad_fixture_fails_with_aimocks_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mock, "START_TIMEOUT_S", 3)
    monkeypatch.setattr(
        mock,
        "fixtures",
        lambda cases, descriptor: {"fixtures": [{"match": {}, "response": {"nope": 1}}]},
    )
    with pytest.raises(Failed, match="didn't start"):
        with mock.serving([case()], DESCRIPTOR):
            pass
