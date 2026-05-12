"""Conformance harness for avp-claude-agent.

The translator's single public entry point is `run()`. Tests use the
SDK-injection seam that `ClaudeAgentTranslator.__init__` already exposes
(`sdk_client_cls`, `sdk_options_cls`, `sdk_hook_matcher_cls`,
`sdk_agent_definition_cls`) to swap the real `claude_agent_sdk.ClaudeSDKClient`
for `_ScriptedSDKClient` — a small class that yields canned messages
and invokes the translator's PreToolUse / PostToolUse hooks at the
points the script specifies. No network, no `claude` CLI.

The case file format is unchanged from the spec's conformance schema.
The harness translates a case's `scripted_model` + `scripted_tools` +
`scripted_resolver` into the SDK-shape stand-ins the translator's
`_on_sdk_message` / hook callbacks already accept.

Matcher / final-state assertion logic is reused from
`avp.conformance.harness` so both harnesses (this one and the reference
`AVPAgent` one) speak the same expectation language.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from avp.agent.mock import ScriptedResolver
from avp.conformance.harness import (
    _ORDERING_FNS,
    CaseFailure,
    CaseResult,
    _check_final_state,
    _trajectory_to_dicts,
)
from avp.conformance.matcher import matches_partial
from avp.types import AgentDescriptor, Commission
from avp_claude_agent.translator import ClaudeAgentTranslator

# ── Duck-typed SDK Message / Block builders ───────────────────────────────────


def _block(class_name: str, **attrs: Any) -> Any:
    """Build an object whose `type(obj).__name__` is `class_name` and
    whose attributes are `attrs`. The translator's `_on_sdk_message`
    and content-block walks dispatch on class name, so this is the
    smallest faithful stand-in."""
    cls = type(class_name, (), {})
    obj = cls()
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def _usage(
    input_tokens: int, output_tokens: int, cache_read: int, cache_write: int
) -> dict[str, int]:
    """Real CASDK passes `usage` as `dict[str, Any] | None`. Match the
    shape so `_compute_cost` can do `usage.get(...)`."""
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
        kwargs = {"thinking": rb.get("text", "")}
        if rb.get("signature"):
            kwargs["signature"] = rb["signature"]
        cls_name = "RedactedThinkingBlock" if rb.get("redacted") else "ThinkingBlock"
        blocks.append(_block(cls_name, **kwargs))
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
        "AssistantMessage",
        content=blocks,
        usage=usage,
        model=model,
        stop_reason=stop_reason,
    )


def _result_message(total_cost_usd: float | None) -> Any:
    return _block("ResultMessage", total_cost_usd=total_cost_usd)


# ── Scripted SDK client ───────────────────────────────────────────────────────


class _ScriptedSDKClient:
    """Drop-in for `claude_agent_sdk.ClaudeSDKClient`. Satisfies the
    same protocol the translator's `_async_invoke_sdk` calls into:

      - async context manager,
      - `connect(prompt)` no-op,
      - `get_context_usage()` returns empty (translator falls back to
        Commission-only enrichment),
      - `get_mcp_status()` returns empty (translator falls back to
        Commission-stub `mcp_server_connected` emission),
      - `receive_response()` yields canned messages and invokes the
        PreToolUse / PostToolUse hooks via `options.hooks` at the
        points the script specifies.

    Instantiated indirectly through `_make_scripted_sdk_client_cls(script)`
    so the translator's `sdk_client_cls(options=options)` call returns
    an instance with the captured script.
    """

    _script: list[dict[str, Any]] = []  # overridden by the per-run subclass

    def __init__(self, *, options: Any) -> None:
        self._options = options

    async def __aenter__(self) -> _ScriptedSDKClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False

    async def connect(self, prompt: str) -> None:
        del prompt
        return None

    async def get_context_usage(self) -> dict[str, Any]:
        return {}

    async def get_mcp_status(self) -> dict[str, Any]:
        return {"mcpServers": []}

    async def receive_response(self) -> AsyncIterator[Any]:
        hooks = getattr(self._options, "hooks", None) or {}
        pre_tool_matchers = hooks.get("PreToolUse") or []
        post_tool_matchers = hooks.get("PostToolUse") or []

        for step in self._script:
            kind = step.get("kind")
            if kind == "sdk_message":
                yield step["message"]
            elif kind == "pre_tool":
                await _invoke_hooks(
                    pre_tool_matchers,
                    {
                        "tool_use_id": step["tool_use_id"],
                        "tool_name": step["tool_name"],
                        "tool_input": step.get("tool_input") or {},
                    },
                    step["tool_use_id"],
                )
            elif kind == "post_tool":
                await _invoke_hooks(
                    post_tool_matchers,
                    {
                        "tool_use_id": step["tool_use_id"],
                        "tool_name": step["tool_name"],
                        "tool_response": step.get("tool_response", ""),
                    },
                    step["tool_use_id"],
                )
            else:
                raise ValueError(f"unknown script step kind {kind!r}")


async def _invoke_hooks(matchers: list[Any], input_data: dict[str, Any], tool_use_id: str) -> None:
    """Walk one matcher list (PreToolUse or PostToolUse) and await each
    hook coroutine the same way the real SDK does."""
    for matcher in matchers:
        for hook in getattr(matcher, "hooks", None) or []:
            await hook(input_data, tool_use_id, None)


def _make_scripted_sdk_client_cls(script: list[dict[str, Any]]) -> type[_ScriptedSDKClient]:
    """Return a `_ScriptedSDKClient` subclass with the script baked into
    a class attribute. The translator calls `sdk_client_cls(options=...)`
    once per run; the closure-via-subclass keeps that call signature
    matching `ClaudeSDKClient` exactly (no options/script positional
    juggling)."""
    return type("_ScriptedSDKClient", (_ScriptedSDKClient,), {"_script": script})


# ── Case-script → translator-script translation ───────────────────────────────


def _scripted_to_translator_script(
    *,
    scripted_model: list[dict[str, Any]],
    scripted_tools: dict[str, dict[str, Any]],
    commission_model: str | None,
    subagent_ids: set[str],
) -> list[dict[str, Any]]:
    """Translate a case's AVP-shape scripted turns into the SDK message
    stream + hook-fire sequence the scripted client replays.

    Per turn:
      1. one AssistantMessage stand-in (TextBlocks + ThinkingBlocks +
         ToolUseBlocks + cumulative-usage dict),
      2. PreToolUse + PostToolUse pair per tool_call.

    Cumulative usage accumulates across turns because the SDK reports
    cumulatives (the translator subtracts the previous to get per-turn
    deltas). A final ResultMessage carries the authoritative total cost.
    """
    script: list[dict[str, Any]] = []
    cum_input = cum_output = cum_cache_read = cum_cache_write = 0
    cum_cost = 0.0

    for turn in scripted_model:
        cum_input += int(turn.get("tokens_input") or 0)
        cum_output += int(turn.get("tokens_output") or 0)
        cum_cache_read += int(turn.get("tokens_cache_read") or 0)
        cum_cache_write += int(turn.get("tokens_cache_write") or 0)
        cum_cost += float(turn.get("cost_usd") or 0.0)

        # Rewrite tool_calls that target a declared subagent. AVPAgent
        # dispatches subagents by name; the Claude Agent SDK routes them
        # through the `Agent` tool with a `subagent_type` input field.
        # The translator recognizes subagent dispatch via that shape.
        rewritten_tool_uses: list[dict[str, Any]] = []
        for tc in turn.get("tool_calls") or []:
            if tc["tool"] in subagent_ids:
                rewritten_tool_uses.append(
                    {
                        "call_id": tc["call_id"],
                        "tool": "Agent",
                        "input": {
                            "subagent_type": tc["tool"],
                            **(tc.get("input") or {}),
                        },
                        "_subagent_original_name": tc["tool"],
                    }
                )
            else:
                rewritten_tool_uses.append(tc)

        # Case-level `refusal` maps to stop_reason + TextBlock content,
        # the same shape Anthropic produces when the model declines.
        refusal = turn.get("refusal") or {}
        text_for_msg = str(turn.get("text") or refusal.get("message") or "")
        stop_reason = turn.get("stop_reason") or (refusal.get("reason") if refusal else None)

        msg = _assistant_message(
            text=text_for_msg,
            tool_uses=rewritten_tool_uses,
            reasoning_blocks=list(turn.get("reasoning_blocks") or []),
            usage=_usage(cum_input, cum_output, cum_cache_read, cum_cache_write),
            model=commission_model,
            stop_reason=stop_reason,
        )
        script.append({"kind": "sdk_message", "message": msg})

        for tc in rewritten_tool_uses:
            tool_name = tc["tool"]
            call_id = tc["call_id"]
            tool_input = tc.get("input") or {}
            # Subagent path: response lookup is by ORIGINAL name (case
            # authors don't know about the Agent-tool rewrite); the
            # spawn outcome comes from scripted_resolver.subagent_spawns
            # via the resolver, not from scripted_tools.
            original = tc.get("_subagent_original_name")
            stub = scripted_tools.get(original or tool_name) or {}
            response: Any = stub.get("output", "")
            script.append(
                {
                    "kind": "pre_tool",
                    "tool_name": tool_name,
                    "tool_use_id": call_id,
                    "tool_input": tool_input,
                }
            )
            script.append(
                {
                    "kind": "post_tool",
                    "tool_name": tool_name,
                    "tool_use_id": call_id,
                    "tool_response": response,
                }
            )

    script.append({"kind": "sdk_message", "message": _result_message(cum_cost)})
    return script


# ── Case execution ────────────────────────────────────────────────────────────


def _has_managed(commission: Commission) -> bool:
    return bool(commission.mcp_servers or commission.skills or commission.subagents)


def _build_translator(case: dict[str, Any]) -> tuple[ClaudeAgentTranslator, list[Any]]:
    """Construct the translator wired with the case's resolver, descriptor,
    and a `_ScriptedSDKClient` subclass that holds the script for this
    case. The translator runs through its normal `run()` path; the script
    drives the SDK side."""
    commission = Commission.model_validate(case["commission"])
    events: list[Any] = []

    sr_cfg = case.get("scripted_resolver") or {}
    resolver: ScriptedResolver | None
    if _has_managed(commission) and not case.get("omit_resolver"):
        resolver = ScriptedResolver(
            resolutions=sr_cfg.get("resolutions") or {},
            subagent_spawns=sr_cfg.get("subagent_spawns") or {},
        )
    else:
        resolver = None

    descriptor_dict = dict(case.get("agent_descriptor") or {})
    # Case-level `agent_builtin_tools` is AVPAgent's constructor-arg shape.
    # The translator reads its built-in catalog from `descriptor.built_in_tools`,
    # so merge the case tools there. Synthesize a minimal descriptor when
    # the case ships builtins but no descriptor.
    case_builtin_tools = case.get("agent_builtin_tools") or []
    if case_builtin_tools:
        descriptor_dict.setdefault("agent_name", "avp-claude-agent-conformance")
        descriptor_dict.setdefault("agent_version", "0.0.0")
        descriptor_dict.setdefault("avp_spec_version", "0.1")
        existing = list(descriptor_dict.get("built_in_tools") or [])
        existing_names = {t.get("name") for t in existing}
        for entry in case_builtin_tools:
            if entry.get("name") not in existing_names:
                existing.append(entry)
        descriptor_dict["built_in_tools"] = existing
    descriptor = AgentDescriptor.model_validate(descriptor_dict) if descriptor_dict else None

    script = _scripted_to_translator_script(
        scripted_model=case.get("scripted_model") or [],
        scripted_tools=case.get("scripted_tools") or {},
        commission_model=commission.model,
        subagent_ids={s.id for s in (commission.subagents or [])},
    )

    # Real CASDK option / hook containers — pure data classes, no
    # network/subprocess side effects on construction.
    # `sdk_agent_definition_cls` is intentionally NOT passed: the real
    # `AgentDefinition` requires a `prompt` field that conformance cases
    # don't supply. The translator's dict-fallback path handles this.
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

    translator = ClaudeAgentTranslator(
        commission=commission,
        on_event=events.append,
        resolver=resolver,
        descriptor=descriptor,
        sdk_client_cls=_make_scripted_sdk_client_cls(script),
        sdk_options_cls=ClaudeAgentOptions,
        sdk_hook_matcher_cls=HookMatcher,
    )
    return translator, events


def run_case(path: Path) -> CaseResult:
    """Execute one case file against the translator and return a CaseResult."""
    case = json.loads(path.read_text())
    case_id = case.get("id") or path.stem
    failures: list[CaseFailure] = []
    traj: list[dict[str, Any]] = []

    t0 = time.monotonic()
    try:
        translator, events = _build_translator(case)
        translator.run()
        traj = _trajectory_to_dicts(events)
    except Exception as exc:
        return CaseResult(
            case_id=case_id,
            path=path,
            passed=False,
            failures=[CaseFailure(label="translator-error", detail=f"{type(exc).__name__}: {exc}")],
            trajectory=traj,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    expectations = case["expectations"]
    matchers = expectations.get("events") or []
    ordering = expectations.get("ordering", "in_order_subsequence")
    fn: Callable[..., tuple[bool, str]] | None = _ORDERING_FNS.get(ordering)
    if fn is None:
        failures.append(
            CaseFailure(label="harness-bug", detail=f"unknown ordering mode {ordering!r}")
        )
    elif matchers:
        ok, msg = fn(matchers, traj)
        if not ok:
            failures.append(CaseFailure(label=f"events ({ordering})", detail=msg))

    for fb in expectations.get("forbidden_events") or []:
        pattern = fb["match"]
        for ev in traj:
            if matches_partial(pattern, ev):
                label = fb.get("label") or "forbidden_events"
                failures.append(
                    CaseFailure(label=f"forbidden: {label}", detail=f"event matched: {ev}")
                )
                break

    if "final_state" in expectations:
        ok, msg = _check_final_state(expectations["final_state"], traj)
        if not ok:
            failures.append(CaseFailure(label="final_state", detail=msg))

    return CaseResult(
        case_id=case_id,
        path=path,
        passed=not failures,
        failures=failures,
        trajectory=traj,
        duration_ms=int((time.monotonic() - t0) * 1000),
    )


def run_suite(cases_dir: Path) -> list[CaseResult]:
    """Execute every *.json case under `cases_dir`, recursively."""
    return [run_case(p) for p in sorted(cases_dir.rglob("*.json"))]
