"""query() and aep_options() — the primary user-facing API."""

from __future__ import annotations

import sys
import uuid
from typing import Any, AsyncIterator, IO

import claude_agent_sdk as _sdk
from claude_agent_sdk import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

from agent_execution_protocol import (
    AepHook,
    emit_agent_start,
    emit_text_output,
    emit_cost_update,
    emit_error,
    emit_agent_stop,
)

from ._hooks import build_tool_hooks, fire_hooks, _ms


DEFAULT_MODEL = "claude-sonnet-4-6"


def aep_options(
    *,
    run_id: str | None = None,
    base: ClaudeAgentOptions | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> tuple[str, ClaudeAgentOptions]:
    """Wrap a ClaudeAgentOptions with AEP-emitting tool hooks.

    Returns ``(run_id, options)`` — pass *options* to :func:`query` as usual.
    The returned ``run_id`` is generated if not provided.

    Example::

        run_id, opts = aep_options(model="claude-sonnet-4-6")
        async for msg in query(prompt="...", options=opts, run_id=run_id):
            ...
    """
    run_id = run_id or str(uuid.uuid4())
    step_ref = [0]
    stop_flag = [False]
    hooks = build_tool_hooks(run_id, step_ref, [], None, stop_flag)

    if base is not None:
        existing = base.hooks or {}
        opts = ClaudeAgentOptions(
            model=base.model or model,
            system_prompt=base.system_prompt,
            max_turns=base.max_turns,
            allowed_tools=base.allowed_tools,
            mcp_servers=base.mcp_servers,
            permission_mode=base.permission_mode,
            hooks={**existing, **hooks},
        )
    else:
        opts = ClaudeAgentOptions(model=model, hooks=hooks, **kwargs)

    return run_id, opts


async def query(
    prompt: str,
    options: ClaudeAgentOptions | None = None,
    *,
    run_id: str | None = None,
    model: str | None = None,
    thread_id: str | None = None,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    tools: list[dict] | None = None,
    aep_hooks: list[AepHook] | None = None,
    hook_stdin: IO[str] | None = None,
) -> AsyncIterator[Any]:
    """Drop-in AEP-enabled replacement for ``claude_agent_sdk.query``.

    Emits AEP events to stdout while yielding the same messages as the
    underlying SDK. All SDK arguments pass through unchanged.

    *aep_hooks* and *hook_stdin* enable supervisor hooks (subprocess mode):
    the runner pauses at each hook trigger, emits a ``hook_request``, reads
    a ``hook_verdict`` from *hook_stdin*, then continues or stops accordingly.

    Example::

        from claude_agent_sdk_aep import query
        from claude_agent_sdk import ClaudeAgentOptions

        async for message in query(
            prompt="Fix the bug in auth.py",
            options=ClaudeAgentOptions(allowed_tools=["Read", "Edit"]),
        ):
            if hasattr(message, "result"):
                print(message.result)
    """
    _run_id = run_id or str(uuid.uuid4())
    _aep_hooks = aep_hooks or []
    step_ref = [0]
    stop_flag = [False]

    sdk_hooks = build_tool_hooks(_run_id, step_ref, _aep_hooks, hook_stdin, stop_flag)

    if options is not None:
        existing = options.hooks or {}
        sdk_opts = ClaudeAgentOptions(
            model=options.model,
            system_prompt=options.system_prompt,
            max_turns=options.max_turns,
            allowed_tools=options.allowed_tools,
            mcp_servers=options.mcp_servers,
            permission_mode=options.permission_mode,
            hooks={**existing, **sdk_hooks},
        )
        _model = _aep_model(options.model or model)
    else:
        sdk_opts = ClaudeAgentOptions(hooks=sdk_hooks)
        _model = _aep_model(model)

    emit_agent_start(
        run_id=_run_id,
        model=_model,
        prompt=prompt,
        system_prompt=options.system_prompt if options else None,
        tools=tools,
        thread_id=thread_id,
        tags=tags or [],
        meta=meta or {},
    )

    # on_start hook — before any model call
    if await fire_hooks("on_start", _run_id, 0, _aep_hooks, hook_stdin) == "stop":
        emit_agent_stop(
            run_id=_run_id,
            reason="supervisor_stopped",
            total_tokens=0,
            total_cost_usd=0.0,
            total_turns=0,
            duration_ms=0,
        )
        return

    run_start = _ms()
    reason = "converged"
    total_cost_usd = 0.0
    total_tokens = 0
    total_turns = 0

    try:
        async for message in _sdk.query(prompt=prompt, options=sdk_opts):
            if stop_flag[0]:
                reason = "supervisor_stopped"
                break

            if isinstance(message, AssistantMessage):
                usage = getattr(message, "usage", None) or {}
                total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

                for block in getattr(message, "content", []):
                    if isinstance(block, TextBlock):
                        text = getattr(block, "text", "")
                        if text.strip():
                            emit_text_output(run_id=_run_id, step=step_ref[0], text=text)

                # on_turn_end hook (also fires `always` hooks via trigger matching)
                if await fire_hooks("on_turn_end", _run_id, step_ref[0], _aep_hooks, hook_stdin) == "stop":
                    reason = "supervisor_stopped"
                    break

            elif isinstance(message, ResultMessage):
                total_cost_usd = getattr(message, "total_cost_usd", 0.0) or 0.0
                total_turns = getattr(message, "num_turns", step_ref[0]) or step_ref[0]
                stop_reason = getattr(message, "stop_reason", None)
                if stop_reason == "max_turns":
                    reason = "turn_limit"
                elif stop_reason == "error":
                    reason = "error"
                emit_cost_update(
                    run_id=_run_id,
                    total_cost_usd=total_cost_usd,
                    total_tokens=total_tokens,
                )

            yield message

    except Exception as e:
        emit_error(run_id=_run_id, code="runner_crash", message=str(e))
        reason = "error"
        raise

    finally:
        emit_agent_stop(
            run_id=_run_id,
            reason=reason,
            total_tokens=total_tokens,
            total_cost_usd=total_cost_usd,
            total_turns=total_turns,
            duration_ms=_ms() - run_start,
        )
        # on_stop hook — after agent_stop, verdict is informational
        await fire_hooks("on_stop", _run_id, step_ref[0], _aep_hooks, hook_stdin)


def _aep_model(model: str | None) -> str:
    """Normalise a model string to AEP vendor-prefixed form."""
    if not model:
        return f"anthropic/{DEFAULT_MODEL}"
    if "/" in model:
        return model
    return f"anthropic/{model}"
