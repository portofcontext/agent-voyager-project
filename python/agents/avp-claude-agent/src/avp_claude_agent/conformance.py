"""Conformance harness for avp-claude-agent.

The translator observes Claude Agent SDK at three boundaries:

  1. SDK client lifecycle — `async with ClaudeSDKClient(options) as c`,
     `c.connect(prompt)`, `c.get_context_usage()`, `c.get_mcp_status()`,
     `async for msg in c.receive_response()`.
  2. Typed messages flowing out of `receive_response()` —
     `AssistantMessage` with `.content` blocks (TextBlock, ThinkingBlock,
     ToolUseBlock, …), `ResultMessage` with `.total_cost_usd`.
  3. Hooks registered via `ClaudeAgentOptions.hooks` — PreToolUse /
     PostToolUse callbacks invoked by the SDK around each tool dispatch.

Conformance has to drive these without a live `claude` CLI / network /
real Anthropic API. This file provides a scripted substitute for each
boundary, plumbed through the translator's existing `sdk_client_cls`
constructor seam. The translator itself is unchanged — `run()` is the
production code path.

  1 → `_ScriptedSDKClient`
  2 → `_assistant_message`, `_result_message`, `_block`
  3 → fired from `_ScriptedSDKClient.receive_response` via `options.hooks`

`_case_to_script` is the boundary between the case file's AVP shape
(per-turn deltas, declarative tool_calls) and CASDK's shape (cumulative
usage on each AssistantMessage, separate hook firings per tool).
`_run_one` is the framework `CaseRunner`: build, run, return events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from avp.conformance.sdk_harness import (
    build_commission,
    build_descriptor,
    build_resolver,
    make_cli,
    run_case,
    run_suite,
)
from avp_claude_agent.translator import ClaudeAgentTranslator

# ── (Boundary 2) Stand-ins for CASDK's typed Messages and Blocks ──────────────
# The translator dispatches on `type(obj).__name__` and reads attributes.
# We construct fresh classes with the right name and bolt the right
# attrs on. Avoids importing CASDK's real Message classes (some have
# constructor requirements we can't satisfy from case-file data alone).


def _block(class_name: str, **attrs: Any) -> Any:
    cls = type(class_name, (), {})
    obj = cls()
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def _usage(
    input_tokens: int, output_tokens: int, cache_read: int, cache_write: int
) -> dict[str, int]:
    # CASDK's `AssistantMessage.usage` is typed `dict[str, Any] | None`,
    # so a plain dict satisfies `_compute_cost(model, usage).get(...)`.
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_write,
    }


def _assistant_message(
    *,
    text: str,
    tool_uses: list[dict[str, Any]],
    reasoning_blocks: list[dict[str, Any]],
    usage: Any,
    model: str | None,
    stop_reason: str | None,
) -> Any:
    blocks: list[Any] = []
    for rb in reasoning_blocks:
        kw = {"thinking": rb.get("text", "")}
        if rb.get("signature"):
            kw["signature"] = rb["signature"]
        blocks.append(
            _block("RedactedThinkingBlock" if rb.get("redacted") else "ThinkingBlock", **kw)
        )
    if text:
        blocks.append(_block("TextBlock", text=text, type="text"))
    for tu in tool_uses:
        blocks.append(
            _block(
                "ToolUseBlock",
                id=tu["call_id"],
                name=tu["tool"],
                input=tu.get("input") or {},
                type="tool_use",
            )
        )
    return _block(
        "AssistantMessage", content=blocks, usage=usage, model=model, stop_reason=stop_reason
    )


def _result_message(total_cost_usd: float | None) -> Any:
    # `_handle_result_message` reads `.total_cost_usd` and emits the
    # final `cost_recorded` tagged `avp.cost.source="reported"`.
    return _block("ResultMessage", total_cost_usd=total_cost_usd)


# ── (Boundary 1 + 3) Scripted SDK client ──────────────────────────────────────
# `_async_invoke_sdk` calls into the SDK client like this:
#
#     async with self._sdk_client_cls(options=options) as client:
#         await client.connect(prompt)
#         # emit middle events (resolution / mcp_connected / skill_loaded)
#         async for message in client.receive_response():
#             self._on_sdk_message(message)
#
# `get_context_usage()` and `get_mcp_status()` are called by the
# middle-events emitters; we return empty so the translator falls back
# to Commission-only state (the bundled built-in catalog + descriptor).
#
# Hooks the translator registered via `options.hooks` fire from inside
# `receive_response`, same as real CASDK fires them — just driven by
# the script instead of real model output.


class _ScriptedSDKClient:
    _script: list[dict[str, Any]] = []  # bound by _scripted_client_cls

    def __init__(self, *, options: Any) -> None:
        self._options = options

    async def __aenter__(self) -> _ScriptedSDKClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False

    async def connect(self, prompt: str) -> None:
        del prompt

    async def get_context_usage(self) -> dict[str, Any]:
        return {}

    async def get_mcp_status(self) -> dict[str, Any]:
        return {"mcpServers": []}

    async def receive_response(self) -> AsyncIterator[Any]:
        hooks = getattr(self._options, "hooks", None) or {}
        pre = hooks.get("PreToolUse") or []
        post = hooks.get("PostToolUse") or []
        for step in self._script:
            kind = step.get("kind")
            if kind == "sdk_message":
                yield step["message"]
            elif kind == "pre_tool":
                await _invoke(pre, _hook_input(step, "tool_input", {}), step["tool_use_id"])
            elif kind == "post_tool":
                await _invoke(post, _hook_input(step, "tool_response", ""), step["tool_use_id"])
            else:
                raise ValueError(f"unknown script step kind {kind!r}")


def _hook_input(step: dict[str, Any], payload_key: str, default: Any) -> dict[str, Any]:
    return {
        "tool_use_id": step["tool_use_id"],
        "tool_name": step["tool_name"],
        payload_key: step.get(payload_key) or default,
    }


async def _invoke(matchers: list[Any], input_data: dict[str, Any], tool_use_id: str) -> None:
    for m in matchers:
        for hook in getattr(m, "hooks", None) or []:
            await hook(input_data, tool_use_id, None)


def _scripted_client_cls(script: list[dict[str, Any]]) -> type[_ScriptedSDKClient]:
    # The translator calls `sdk_client_cls(options=options)` — match
    # that signature by baking the script into a subclass attribute.
    return type("_ScriptedSDKClient", (_ScriptedSDKClient,), {"_script": script})


# ── AVP case shape → CASDK event stream ───────────────────────────────────────
# Two shape mismatches the translator hides from production callers but
# the harness has to bridge:
#
#  - usage:    cases declare per-turn deltas; CASDK reports cumulative
#              on each AssistantMessage (translator subtracts to recover
#              the delta). We accumulate across turns here.
#  - subagent: cases dispatch a subagent by its id (`tool: "researcher"`);
#              CASDK routes through the `Agent` tool with `subagent_type:
#              "researcher"`. We rewrite at this boundary.
#
# Refusals (`turn["refusal"]`) map to CASDK's `stop_reason="refusal"` plus
# a TextBlock carrying the refusal message.


def _case_to_script(
    *,
    scripted_model: list[dict[str, Any]],
    scripted_tools: dict[str, dict[str, Any]],
    commission_model: str | None,
    subagent_ids: set[str],
) -> list[dict[str, Any]]:
    script: list[dict[str, Any]] = []
    ci = co = ccr = ccw = 0
    cum_cost = 0.0

    for turn in scripted_model:
        ci += int(turn.get("tokens_input") or 0)
        co += int(turn.get("tokens_output") or 0)
        ccr += int(turn.get("tokens_cache_read") or 0)
        ccw += int(turn.get("tokens_cache_write") or 0)
        cum_cost += float(turn.get("cost_usd") or 0.0)

        tool_uses: list[dict[str, Any]] = []
        for tc in turn.get("tool_calls") or []:
            if tc["tool"] in subagent_ids:
                tool_uses.append(
                    {
                        "call_id": tc["call_id"],
                        "tool": "Agent",
                        "input": {"subagent_type": tc["tool"], **(tc.get("input") or {})},
                        "_orig": tc["tool"],
                    }
                )
            else:
                tool_uses.append(tc)

        refusal = turn.get("refusal") or {}
        text = str(turn.get("text") or refusal.get("message") or "")
        stop_reason = turn.get("stop_reason") or (refusal.get("reason") if refusal else None)

        script.append(
            {
                "kind": "sdk_message",
                "message": _assistant_message(
                    text=text,
                    tool_uses=tool_uses,
                    reasoning_blocks=list(turn.get("reasoning_blocks") or []),
                    usage=_usage(ci, co, ccr, ccw),
                    model=commission_model,
                    stop_reason=stop_reason,
                ),
            }
        )
        for tc in tool_uses:
            # Subagent path: tool_response lookup is by ORIGINAL name in
            # scripted_tools (case authors don't know about the rewrite);
            # spawn outcomes come from scripted_resolver.subagent_spawns
            # via the resolver, not from scripted_tools.
            stub = scripted_tools.get(tc.get("_orig") or tc["tool"]) or {}
            script.append(
                {
                    "kind": "pre_tool",
                    "tool_name": tc["tool"],
                    "tool_use_id": tc["call_id"],
                    "tool_input": tc.get("input") or {},
                }
            )
            script.append(
                {
                    "kind": "post_tool",
                    "tool_name": tc["tool"],
                    "tool_use_id": tc["call_id"],
                    "tool_response": stub.get("output", ""),
                }
            )

    script.append({"kind": "sdk_message", "message": _result_message(cum_cost)})
    return script


# ── One case: framework `CaseRunner` ──────────────────────────────────────────
# Given the case dict, wire the translator with this case's resolver +
# descriptor + scripted SDK client + scripted options. The translator
# runs through its normal `run()` path; the framework handles the
# expectation evaluation and reporting on the events we return.


def _run_one(case: dict[str, Any]) -> list[Any]:
    # CASDK option / hook containers — pure data classes, no network /
    # subprocess side effects on construction. `AgentDefinition` is
    # intentionally NOT passed: its required `prompt` field isn't in
    # conformance cases, and the translator's dict-fallback path
    # handles that case (see `_build_sdk_agents`).
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

    commission = build_commission(case)
    events: list[Any] = []
    script = _case_to_script(
        scripted_model=case.get("scripted_model") or [],
        scripted_tools=case.get("scripted_tools") or {},
        commission_model=commission.model,
        subagent_ids={s.id for s in (commission.subagents or [])},
    )
    translator = ClaudeAgentTranslator(
        commission=commission,
        on_event=events.append,
        resolver=build_resolver(case, commission),
        descriptor=build_descriptor(case),
        sdk_client_cls=_scripted_client_cls(script),
        sdk_options_cls=ClaudeAgentOptions,
        sdk_hook_matcher_cls=HookMatcher,
    )
    translator.run()
    return events


main = make_cli(
    runner=_run_one,
    prog="avp-claude-agent-conformance",
    description="Run v0.1 conformance cases against ClaudeAgentTranslator.",
)


def run_case_for_path(path):
    return run_case(path, _run_one)


def run_suite_for_path(path):
    return run_suite(path, _run_one)


__all__ = ["main", "run_case_for_path", "run_suite_for_path"]
