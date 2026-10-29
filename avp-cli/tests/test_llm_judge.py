"""Eval config -> vault -> real provider SDK -> HTTP -> judge score."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from avp.commission import Commission
from avp_cli import config, library, vault
from avp_cli.eval.scoring import FinalOutput
from avp_cli.observability import Summary

pytest.importorskip("pydantic_ai")


@pytest.fixture
def upstream():
    seen = []
    state = {"error": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            seen.append((self.path, dict(self.headers), body))
            verdict = "correct: yes\nconfidence: 100"
            if state["error"]:
                response = {
                    "error": {
                        "message": "invalid key saved-judge-key",
                        "type": "invalid_request_error",
                    }
                }
            elif self.path.split("?")[0].endswith("/messages"):
                response = {
                    "id": "msg_judge",
                    "type": "message",
                    "role": "assistant",
                    "model": body["model"],
                    "content": [{"type": "text", "text": verdict}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 8},
                }
            elif ":generateContent" in self.path:
                response = {
                    "candidates": [
                        {
                            "content": {"role": "model", "parts": [{"text": verdict}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "candidatesTokenCount": 8,
                        "totalTokenCount": 18,
                    },
                    "modelVersion": "gemini-2.5-flash",
                }
            elif self.path.endswith("/responses"):
                response = {
                    "id": "resp_judge",
                    "object": "response",
                    "created_at": 1,
                    "status": "completed",
                    "model": body["model"],
                    "output": [
                        {
                            "id": "msg_judge",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {"type": "output_text", "text": verdict, "annotations": []}
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 8, "total_tokens": 18},
                }
            else:
                response = {
                    "id": "chat_judge",
                    "provider": "test-provider",
                    "object": "chat.completion",
                    "created": 1,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": verdict},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
                }
            payload = json.dumps(response).encode()
            self.send_response(400 if state["error"] else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _eval(tmp_path, monkeypatch, base_url, model, provider):
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    for name in ("AVP_VAULT_JUDGE_TEST", "JUDGE_TEST"):
        monkeypatch.delenv(name, raising=False)
    # A configured vault reference must win over native SDK environment keys.
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.setenv(name, "wrong-environment-key")
    vault.store("judge-test", "saved-judge-key")
    library.save(
        "baseline", Commission(schema_version="0.1", run_id="baseline", model="test/agent")
    )
    spec = {
        "name": "llm-judge",
        "model": model,
        "max_tokens": 4096,
        "provider": {"id": provider, "base_url": base_url, "credential": {"vault": "judge-test"}},
    }
    if base_url is None:
        del spec["provider"]["base_url"]
    ev = config.eval_from_dict(
        {
            "dataset": {
                "source": "inline",
                "items": [{"prompt": "What is two plus two?", "expected": "4"}],
            },
            "scorer": spec,
            "commissions": ["baseline"],
        }
    )
    assert "saved-judge-key" not in repr(ev.scorer)
    assert "saved-judge-key" not in json.dumps(spec)
    return ev


@pytest.mark.parametrize(
    ("model", "provider", "endpoint", "header", "auth", "api_model"),
    [
        (
            "openai/gpt-5-mini",
            "openai",
            "/v1/responses",
            "authorization",
            "Bearer saved-judge-key",
            "gpt-5-mini",
        ),
        (
            "anthropic/claude-haiku-4-5",
            "anthropic",
            "/v1/messages",
            "x-api-key",
            "saved-judge-key",
            "claude-haiku-4-5",
        ),
        (
            "google/gemini-2.5-flash",
            "google",
            "/v1beta/models/gemini-2.5-flash:generateContent",
            "x-goog-api-key",
            "saved-judge-key",
            None,
        ),
        (
            "anthropic/claude-haiku-4-5",
            "openrouter",
            "/v1/chat/completions",
            "authorization",
            "Bearer saved-judge-key",
            "anthropic/claude-haiku-4-5",
        ),
        (
            "custom/vendor/new-model",
            "openai-chat",
            "/v1/chat/completions",
            "authorization",
            "Bearer saved-judge-key",
            "vendor/new-model",
        ),
    ],
)
def test_judge_provider_request_and_saved_auth(
    tmp_path, monkeypatch, upstream, model, provider, endpoint, header, auth, api_model
):
    base, seen, _ = upstream
    base_url = base if provider in ("google", "anthropic") else base + "/v1"
    if provider == "openrouter":
        # This SDK uses a fixed endpoint. Redirect that endpoint for the test;
        # custom OpenAI-compatible URLs use provider.id = openai-chat.
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        monkeypatch.setattr(OpenRouterProvider, "base_url", property(lambda _: base + "/v1"))
        base_url = None
    ev = _eval(tmp_path, monkeypatch, base_url, model, provider)

    def score(_):
        return ev.scorer.score(
            ev.dataset.items[0], FinalOutput("4", None, "converged"), Summary(run_id="test")
        )

    # Repeat on different worker event loops: no shared or closed SDK clients.
    with ThreadPoolExecutor(max_workers=2) as pool:
        scores = list(pool.map(score, range(3)))
    assert all(s.passed and s.value == 1 for s in scores), scores
    assert len(seen) == 3
    for path, headers, body in seen:
        assert path.split("?")[0] == endpoint
        assert {k.lower(): v for k, v in headers.items()}[header] == auth
        if api_model:
            assert body["model"] == api_model
        assert "two plus two" in json.dumps(body)
        assert "[response]: 4" in json.dumps(body)
        assert "[correct_answer]: 4" in json.dumps(body)
        assert 4096 in (
            body.get("max_tokens"),
            body.get("max_completion_tokens"),
            body.get("max_output_tokens"),
            body.get("generationConfig", {}).get("maxOutputTokens"),
        )


def test_judge_error_does_not_persist_credentials(tmp_path, monkeypatch, upstream):
    base, _, state = upstream
    ev = _eval(tmp_path, monkeypatch, base + "/v1", "openai/gpt-5-mini", "openai")
    state["error"] = True
    score = ev.scorer.score(
        ev.dataset.items[0], FinalOutput("4", None, "converged"), Summary(run_id="test")
    )
    assert not score.passed
    assert "grader error" in score.detail
    assert "saved-judge-key" not in score.detail


def test_judge_picks_up_rotated_saved_key(tmp_path, monkeypatch, upstream):
    base, seen, _ = upstream
    ev = _eval(tmp_path, monkeypatch, base + "/v1", "openai/gpt-5-mini", "openai")
    vault.store("judge-test", "rotated-key")
    score = ev.scorer.score(
        ev.dataset.items[0], FinalOutput("4", None, "converged"), Summary(run_id="test")
    )
    assert score.passed
    assert {k.lower(): v for k, v in seen[0][1].items()}["authorization"] == "Bearer rotated-key"
