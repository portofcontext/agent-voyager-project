"""Run a built-in agent's sandbox image end to end against a stub model.

`make check` drives agents through ping and describe, which never reach a
model. This builds the image a run would use (the same container recipe, on
the default environment image), runs the agent's `run` command in it against a
local server that answers like the provider's API, and requires the run to
converge on the stub's reply. That covers installing the agent exactly as users
get it and building a real request on its provider SDK, so a release that
installs but can't run fails here. No API key and no model cost.

Two sources, both following the release's avp-release.json:

  --from DIR         a release's artifacts before they are published (the
                     release workflows run this, then publish only on success;
                     `make build-agents` writes the same layout)
  --release VERSION  a published release, downloaded as `avp agent install`
                     would (defaults to the CLI's pin)

Usage: uv run python avp/scripts/smoke-agent.py <agent>... (--from DIR | --release [VERSION])
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from avp.launch import directory_env
from avp_cli import agent_install, paths, release_manifest
from avp_cli.agent import _endpoint_env
from avp_cli.agents import AGENT_SOURCES, release_repo, release_url
from avp_cli.environment import Environment
from avp_cli.images import ensure_image

REPLY = "avp-smoke-ok"

# The provider each agent runs on here: its default where it has one.
MODELS = {
    "goose": "anthropic/claude-haiku-4-5",
    "claude-code": "anthropic/claude-haiku-4-5",
    "pi": "anthropic/claude-haiku-4-5",
    "opencode": "anthropic/claude-haiku-4-5",
    "deep-agents": "anthropic/claude-haiku-4-5",
    "pydantic-ai": "anthropic/claude-haiku-4-5",
    "codex": "openai/gpt-5-mini",
    "openai-agents": "openai/gpt-5-mini",
    "gemini-cli": "google/gemini-3.1-flash-lite",
}


def _sse(events: list[tuple[str | None, dict | str]]) -> bytes:
    out = []
    for name, data in events:
        body = data if isinstance(data, str) else json.dumps(data)
        out.append((f"event: {name}\n" if name else "") + f"data: {body}\n\n")
    return "".join(out).encode()


def _anthropic(model: str, stream: bool) -> tuple[str, bytes]:
    usage = {"input_tokens": 1, "output_tokens": 1}
    message = {
        "id": "msg_smoke",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": REPLY}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": usage,
    }
    if not stream:
        return "application/json", json.dumps(message).encode()
    start = {**message, "content": [], "stop_reason": None, "usage": {**usage, "output_tokens": 0}}
    return "text/event-stream", _sse(
        [
            ("message_start", {"type": "message_start", "message": start}),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": REPLY},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 1},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )


def _chat(model: str, stream: bool) -> tuple[str, bytes]:
    usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    base = {"id": "chatcmpl-smoke", "created": 0, "model": model}
    if not stream:
        body = {
            **base,
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": REPLY},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        }
        return "application/json", json.dumps(body).encode()
    chunk = {**base, "object": "chat.completion.chunk"}
    return "text/event-stream", _sse(
        [
            (
                None,
                {
                    **chunk,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": REPLY},
                            "finish_reason": None,
                        }
                    ],
                },
            ),
            (None, {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
            (None, {**chunk, "choices": [], "usage": usage}),
            (None, "[DONE]"),
        ]
    )


def _responses(model: str, stream: bool) -> tuple[str, bytes]:
    part = {"type": "output_text", "text": REPLY, "annotations": []}
    item = {
        "id": "msg_smoke",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [part],
    }
    usage = {
        "input_tokens": 1,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": 1,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 2,
    }
    response = {
        "id": "resp_smoke",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": model,
        "output": [item],
        "usage": usage,
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "metadata": {},
        "parallel_tool_calls": True,
        "temperature": 1.0,
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1.0,
    }
    if not stream:
        return "application/json", json.dumps(response).encode()
    pending = {**response, "status": "in_progress", "output": [], "usage": None}
    ids = {"item_id": item["id"], "output_index": 0, "content_index": 0}
    events = [
        ("response.created", {"response": pending}),
        ("response.in_progress", {"response": pending}),
        (
            "response.output_item.added",
            {"output_index": 0, "item": {**item, "status": "in_progress", "content": []}},
        ),
        ("response.content_part.added", {**ids, "part": {**part, "text": ""}}),
        ("response.output_text.delta", {**ids, "delta": REPLY, "logprobs": []}),
        ("response.output_text.done", {**ids, "text": REPLY, "logprobs": []}),
        ("response.content_part.done", {**ids, "part": part}),
        ("response.output_item.done", {"output_index": 0, "item": item}),
        ("response.completed", {"response": response}),
    ]
    return "text/event-stream", _sse(
        [
            (name, {"type": name, "sequence_number": i, **data})
            for i, (name, data) in enumerate(events)
        ]
    )


def _gemini(model: str, stream: bool) -> tuple[str, bytes]:
    body = {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": REPLY}]},
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2},
        "modelVersion": model,
    }
    if not stream:
        return "application/json", json.dumps(body).encode()
    return "text/event-stream", _sse([(None, body)])


class StubModel:
    """A local server that answers the Anthropic, OpenAI, and Gemini APIs with
    one fixed text reply. `requests` lists the paths it served."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.srv = ThreadingHTTPServer(("0.0.0.0", 0), self._handler())
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def _handler(self):
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code: int, ctype: str, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                stub.requests.append(f"GET {self.path}")
                if self.path.split("?")[0].rstrip("/").endswith("/models"):
                    return self._send(200, "application/json", b'{"object":"list","data":[]}')
                return self._send(404, "application/json", b'{"error":"not found"}')

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                path = self.path.split("?")[0]
                stub.requests.append(f"POST {self.path}")
                try:
                    req = json.loads(raw or b"{}")
                except ValueError:
                    req = {}
                model = str(req.get("model", "stub"))
                stream = bool(req.get("stream"))
                if path.endswith("/messages/count_tokens"):
                    return self._send(200, "application/json", b'{"input_tokens":1}')
                if path.endswith("/messages"):
                    return self._send(200, *_anthropic(model, stream))
                if path.endswith("/chat/completions"):
                    return self._send(200, *_chat(model, stream))
                if path.endswith("/responses"):
                    return self._send(200, *_responses(model, stream))
                if ":generateContent" in path or ":streamGenerateContent" in path:
                    model = path.rsplit("/", 1)[-1].split(":")[0]
                    return self._send(200, *_gemini(model, ":stream" in path))
                if path.endswith(":countTokens"):
                    return self._send(200, "application/json", b'{"totalTokens":1}')
                return self._send(404, "application/json", b'{"error":"not found"}')

        return H


def _mountable() -> Path:
    """A directory Docker can bind-mount: under ~/.avp, as `avp run` uses
    (Docker Desktop doesn't share macOS's per-user temp directories)."""
    d = paths.avp_home() / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _recipe(name: str, args: argparse.Namespace):
    if args.from_dir:
        d = Path(args.from_dir).resolve()
        m = release_manifest.load(d / release_manifest.FILENAME)
        if m.agent != name:
            raise SystemExit(f"{d} holds a build of {m.agent}, not {name}")
        print(f"→ {name}: {m.version} from {d}")
        return release_manifest.container_recipe(m, artifacts=d)
    source = AGENT_SOURCES[name]
    repo = release_repo()
    tag, _, assets = agent_install._resolve_release(source, args.release or source.version, repo)
    urls = {a["name"]: a["browser_download_url"] for a in assets}
    if release_manifest.FILENAME not in urls:
        raise SystemExit(f"{tag} has no {release_manifest.FILENAME}")
    print(f"→ {name}: {tag}")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / release_manifest.FILENAME
        agent_install._download(urls[release_manifest.FILENAME], path)
        m = release_manifest.load(path)
    return release_manifest.container_recipe(m, url=release_url(repo, tag))


def smoke(name: str, args: argparse.Namespace) -> bool:
    recipe = _recipe(name, args)
    image = ensure_image(Environment(), recipe, on_line=lambda line: print("  " + line))
    model = MODELS[name]
    provider = model.split("/", 1)[0]
    stub = StubModel()
    dirs = directory_env(Path("/avp"), Path("/avp/workspace"))
    env = {
        **dirs,
        **_endpoint_env(provider, f"http://host.docker.internal:{stub.port}"),
        f"{provider.upper()}_API_KEY": "avp-smoke",
        "GOOSE_PROVIDER": provider,
        **dict(recipe.env),
    }
    commission = {
        "schema_version": "0.1",
        "run_id": "smoke",
        "model": model,
        "prompt": "Reply with a short greeting.",
    }
    with tempfile.TemporaryDirectory(dir=_mountable()) as tmp:
        io, workspace = Path(tmp) / "io", Path(tmp) / "workspace"
        io.mkdir()
        workspace.mkdir()
        (io / "commission.json").write_text(json.dumps(commission))
        argv = [
            "docker",
            "run",
            "--rm",
            "--add-host=host.docker.internal:host-gateway",
            "-v",
            f"{io}:/avp/io",
            "-v",
            f"{workspace}:/avp/workspace",
            *[x for k, v in env.items() for x in ("-e", f"{k}={v}")],
            "--entrypoint",
            "sh",
            image,
            "-c",
            # As `avp run` does: create the state directories, then run.
            f'mkdir -p {shlex.join(dict.fromkeys(dirs.values()))} && exec "$@"',
            "sh",
            *recipe.command,
            "run",
            "--commission",
            "/avp/io/commission.json",
            "--out",
            "/avp/io/trajectory.ndjson",
        ]
        print(f"→ {name}: running {image} against the stub model ({model})")
        result = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        stub.srv.shutdown()
        traj = io / "trajectory.ndjson"
        events = (
            [json.loads(line) for line in traj.read_text().splitlines()] if traj.exists() else []
        )
    stopped = [e["data"] for e in events if e.get("type") == "avp.agent_stopped"]
    errors = [
        e["data"].get("avp.error.message") for e in events if e.get("type") == "avp.error_occurred"
    ]
    reason = stopped[-1].get("avp.reason") if stopped else None
    output = str(stopped[-1].get("avp.output", "")) if stopped else ""
    ok = result.returncode == 0 and reason == "converged" and REPLY in output
    if ok:
        print(f"✓ {name}: converged on the stub's reply ({len(stub.requests)} model requests)")
        return True
    print(f"✗ {name}: exit {result.returncode}, stopped {reason!r}, output {output[:200]!r}")
    for err in errors:
        print(f"  error: {err}")
    print(f"  model requests: {stub.requests or 'none'}")
    for line in (result.stderr or "").splitlines()[-30:]:
        print(f"  {line}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("agents", nargs="+", choices=sorted(AGENT_SOURCES))
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--from", dest="from_dir", help="a directory laid out like a release (one agent)"
    )
    src.add_argument(
        "--release",
        nargs="?",
        const="",
        help="a published version (default: the CLI's pin)",
    )
    args = parser.parse_args()
    if args.from_dir and len(args.agents) > 1:
        parser.error("--from takes one agent")
    failed = [name for name in args.agents if not smoke(name, args)]
    if failed:
        print(f"\nsmoke failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
