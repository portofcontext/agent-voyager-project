# Todo

[] ensure EVERYTHING is emitted on aep
[] review the SDKs. if we stick with the import replacement, make sure the args are matching the actual anthropic sdks and are backwards compatable. review braintrust strategy as a better way to handle event capture. fork braintrust?

## Gaps identified from reviewing claude-agent-sdk-demos
ref: https://github.com/anthropics/claude-agent-sdk-demos

[] **subagent parent-child linking** — multi-agent demos (research-agent) use `parent_tool_use_id` to link child tool calls back to the parent turn. AEP has no way to reconstruct a delegation tree from the event stream. At minimum, `agent_start` needs a `parent_run_id` / `parent_tool_use_id` field.

[] **session lifecycle** — v2 demos (hello-world-v2, simple-chat-app) use `createSession()` / `resumeSession()`. today `run_id` maps to a single run; there's no AEP concept of a session that spans multiple runs. need `session_created` / `session_resumed` events or session fields on `agent_start`.

[] **user interaction blocking** — ask-user-question demo blocks mid-turn waiting for a human response. this is approximated by hooks today but there's no distinct event marking "agent paused waiting for human" vs. "agent paused waiting for tool". different latency profile and SLA meaning.
