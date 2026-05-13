# avp-ollama

AVP v0.1 agent backed by [Ollama](https://ollama.com).

**Scope:** intentionally minimal. This runner exists primarily to demonstrate
supervisor-orchestrated **execution-backend rescue** — see
`portofcontext/RESCUE_PLAN.md` and `spec/v0.1/trajectory.md` §7.3. It emits the
AVP prelude, drives a single (multi-turn-capable) Ollama chat loop, and
emits a conforming `agent_stopped`.

What it does **not** do (vs. `avp-claude-agent`):

- No tool calls. Ollama's tool-use surface is model-specific and out of scope
  for the rescue demo.
- No managed-asset resolution (no `mcp_servers`, no `subagents`, no `skills`).
- No live SDK lifecycle bridging — we drive the chat loop directly.
- No streaming → fine-grained `text_emitted` events. We emit one `text_emitted`
  per turn with the full assistant message.

## Failure injection

The runner honors a `RESCUE_FAIL_AT` env var, used by the rescue smoke test to
provoke a runner failure mid-trajectory:

| Value | Behavior |
|---|---|
| unset | Normal run, no injected failure. |
| `now` | Fail immediately after `agent_started`. |
| `turn:N` | Fail at the start of turn N (1-indexed). If the conversation converges before reaching turn N (common for no-tools prompts that complete in one turn), the failure fires right before `agent_stopped` instead — so the demo always gets a rescue scenario. Set `OLLAMA_FORCE_TURNS=M` (M ≥ N) to make the rescue fire from the realistic "before turn N starts" path. |
| `prob:0.5` | Fail at each turn with probability 0.5. |

## Multi-turn behavior (`OLLAMA_FORCE_TURNS`)

Ollama's non-streaming `/api/chat` returns `done: true` after every response,
so without help the translator exits after turn 1. For demos that need an
actual multi-turn trajectory:

| Value | Behavior |
|---|---|
| unset / `0` | Normal: exit when the model signals `done`. |
| `N` (≥1) | Run exactly N turns. Between turns the translator appends a synthetic user-role message (`OLLAMA_CONTINUATION_PROMPT`, default "Continue with the next step. Be brief.") to keep the model generating. |

This lets `RESCUE_FAIL_AT=turn:2` fire from the realistic "fail before turn 2
starts" code path on a genuinely multi-turn conversation, rather than the
short-prompt fall-through.

## Warm rescue (reads `Commission.resume`)

When the supervisor re-dispatches a rescued run, it attaches a `Commission.resume`
block carrying:

- `from_seq` — where the new runner starts emitting (no events `seq <= from_seq`).
- `context.messages` — reconstructed conversation up to the rescue point.
- `tool_cache` — prior tool invocations, replayed on cache hit instead of re-executed.

`avp-ollama` honors the contract: skips the prelude, inherits the original agent span,
seeds its model call from `context.messages` instead of the Commission's `prompt`, and
short-circuits tool invocations that match the cache.

## Test instrumentation (warm-rescue smoke)

The warm-rescue T2 / T3 smoke tests need deterministic ways to introduce
recall tokens and tool calls into the trajectory. Two demo-only env vars
do that:

| Env var | Format | What it does |
|---|---|---|
| `OLLAMA_INJECT_USER_MESSAGE_AT` | `turn:N:content` | After turn N completes, inject `{role: user, content}` into the conversation **and** emit it as a `text_emitted{role: user}` event. The next turn's model call sees the message. The supervisor's resume-block reconstruction picks it up so a rescued runner inherits it. Content may contain colons. |
| `OLLAMA_INJECT_TOOL_CALL_AT` | `turn:N:tool_name:args_json` | Before turn N, emit a `tool_invoked` event for `tool_name` with `args_json` (must be valid JSON). The translator then either returns from the rescue `tool_cache` (cache hit) or executes the stub `echo` registry (cache miss). |

These are **not** real agent behaviors — they're test scaffolding (same shape as `RESCUE_FAIL_AT`). Real agents drive tool calls and user messages from the model + user, respectively.

### Stub tool registry

Minimal — just `echo(args) -> args`. Anything else returns `{"_stub": true, "tool_name", "args"}`. Used by the smoke to prove that the tool-cache replay path actually short-circuits an invocation post-rescue. Real tool dispatch lands when `avp-ollama` grows real tool support.

On injected failure the runner emits:

```
avp.error_occurred
  data["avp.error.code"]    = "execution_backend_failure"
  data["avp.error.message"] = <description>
```

…and exits **without** emitting `agent_stopped`. The supervisor sees the
`execution_backend_failure` code and triggers a rescue
(`POST /api/runs/{run_id}/rescue` → re-dispatch on a fallback backend).

## Dispatch surface

`avp-ollama-runner` starts a FastAPI server on `OLLAMA_RUNNER_PORT`
(default `8081`). The supervisor's `LocalOllamaBackend` POSTs
`{run_id, environment, resolver?}` to `/` and the runner spawns a background
task to drive the run, returning `{call_id, status: "spawned"}` immediately.

Configuration env vars:

| Var | Purpose | Default |
|---|---|---|
| `OLLAMA_RUNNER_PORT` | FastAPI bind port | `8081` |
| `OLLAMA_HOST` | Ollama HTTP base | `http://localhost:11434` |
| `OLLAMA_MODEL_DEFAULT` | Used when the Commission `model` is empty/unknown | `llama3.2:3b` |
| `SUPERVISOR_BASE_URL` | Where events get posted | `http://localhost:5150` |
| `SUPERVISOR_PROXY_TOKEN` | Optional bearer for the supervisor | unset |
| `RESCUE_FAIL_AT` | Failure injection (see above) | unset |
| `OLLAMA_MAX_TURNS` | Safety cap | `8` |

## Quick start

```bash
# Terminal 1 — Ollama
ollama serve
ollama pull llama3.2:3b

# Terminal 2 — supervisor (with rescue enabled)
SUPERVISOR_RESCUE_ENABLED=1 \
SUPERVISOR_RESCUE_FALLBACK='local-ollama:modal-sandbox' \
OLLAMA_DISPATCH_URL=http://localhost:8081/ \
cargo loco start

# Terminal 3 — the ollama runner
uv run --package avp-ollama avp-ollama-runner

# Terminal 4 — dispatch a run that fails on turn 2
supervisor run dispatch \
  --env demo --runner local-ollama \
  --prompt "tell me a short story" \
  ...
```

See `worker/smoke_test_rescue.sh` (phase 1.4) for the end-to-end demo.
