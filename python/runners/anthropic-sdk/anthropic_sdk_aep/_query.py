"""query() — AEP-instrumented agentic loop using the Anthropic Python SDK."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Callable

import anthropic

from agent_execution_protocol import (
    emit_agent_start,
    emit_agent_stop,
    emit_cost_update,
    emit_error,
    emit_model_turn_end,
    emit_model_turn_start,
    emit_skill_execute,
    emit_skill_read,
    emit_text_output,
    emit_tool_call,
    emit_tool_result,
)


DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_STEPS = 20

# Approximate pricing per million tokens (input / output / cache_read / cache_write).
# Cache read is ~10% of input price; cache write is ~125% of input price.
_PRICING: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-4-6": (15.00, 75.00, 1.50, 18.75),
    "claude-sonnet-4-6": (3.00, 15.00, 0.30, 3.75),
    "claude-haiku-4-5": (0.25, 1.25, 0.03, 0.30),
    "claude-haiku-4-5-20251001": (0.25, 1.25, 0.03, 0.30),
}
_DEFAULT_PRICING = (3.00, 15.00, 0.30, 3.75)

# Built-in code_execution tool required for Anthropic Agent Skills.
_CODE_EXECUTION_TOOL: dict = {
    "type": "code_execution_20250522",
    "name": "code_execution",
}


def _compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """Return estimated cost in USD for one API call."""
    base = model.split("/", 1)[-1]
    for known in _PRICING:
        if base.startswith(known) or base == known:
            p_in, p_out, p_cr, p_cw = _PRICING[known]
            break
    else:
        p_in, p_out, p_cr, p_cw = _DEFAULT_PRICING

    return (
        p_in * input_tokens / 1_000_000
        + p_out * output_tokens / 1_000_000
        + p_cr * cache_read / 1_000_000
        + p_cw * cache_write / 1_000_000
    )


async def query(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    tools: list[dict] | None = None,
    tool_handlers: dict[str, Callable[[dict], Any]] | None = None,
    skills: list[dict] | None = None,
    system_prompt: str | None = None,
    run_id: str | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    thread_id: str | None = None,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> AsyncGenerator[anthropic.types.Message, None]:
    """Run an agentic loop using the Anthropic SDK with AEP event emission.

    *tools* is the standard Anthropic SDK tool list — the same dicts you would
    pass to ``client.messages.create(tools=...)``.  *tool_handlers* maps tool
    names to the Python callables that execute them.

    *skills* enables Anthropic Agent Skills (beta).  Pass a list of skill dicts,
    e.g. ``[{"type": "anthropic", "skill_id": "pptx", "version": "latest"}]``.
    When provided, the runner loads skills via the beta API, emits a
    ``skill_read`` event for each, and emits ``skill_execute`` events whenever
    the model invokes a skill via a ``server_tool_use`` block.

    Yields raw :class:`anthropic.types.Message` objects so callers can inspect
    the full response if needed. AEP events are emitted to stdout as a side
    effect throughout the loop.

    Example (plain tool use)::

        from anthropic_aep import query

        tools = [
            {
                "name": "get_weather",
                "description": "Get the current weather for a city.",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
        ]

        async for message in query(
            prompt="What's the weather in Paris?",
            tools=tools,
            tool_handlers={"get_weather": lambda inp: f"Sunny in {inp['city']}"},
        ):
            pass
    """
    _run_id = run_id or str(uuid.uuid4())
    _handlers = tool_handlers or {}
    _use_skills = bool(skills)

    client = (
        anthropic.AsyncAnthropic(api_key=api_key)
        if api_key
        else anthropic.AsyncAnthropic()
    )

    messages: list[dict] = [{"role": "user", "content": prompt}]

    total_cost = 0.0
    total_input = 0
    total_output = 0
    step = 0
    run_start = time.monotonic()
    stop_reason = "converged"

    # Resolve skill names for emit_agent_start metadata.
    skill_names: list[str] | None = None
    if _use_skills:
        skill_names = [s.get("skill_id", str(s)) for s in (skills or [])]

    emit_agent_start(
        run_id=_run_id,
        model=model,
        prompt=prompt,
        system_prompt=system_prompt,
        tools=[t["name"] for t in (tools or [])] or None,
        thread_id=thread_id,
        tags=tags or [],
        meta={**(meta or {}), **({"skills": skill_names} if skill_names else {})},
    )

    # Emit skill_read for each Anthropic Agent Skill at startup.
    if _use_skills:
        for skill in skills or []:
            emit_skill_read(
                run_id=_run_id,
                step=0,
                name=skill.get("skill_id", str(skill)),
                source=skill.get("type"),
            )

    try:
        while step < max_steps:
            step += 1
            turn_start = time.monotonic()

            emit_model_turn_start(
                run_id=_run_id, step=step, context_messages=len(messages)
            )

            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            }

            # Merge user tools with the code_execution tool needed for Skills.
            all_tools = list(tools or [])
            if _use_skills:
                all_tools.append(_CODE_EXECUTION_TOOL)
                kwargs["container"] = {"type": "persistent", "skills": skills}
                kwargs["betas"] = ["skills-2025-10-02", "code-execution-2025-08-25"]

            if all_tools:
                kwargs["tools"] = all_tools
            if system_prompt:
                kwargs["system"] = system_prompt

            # Use streaming so we can observe server_tool_use (Anthropic Skills)
            # in real time as the model produces content blocks.
            server_tool_uses: list[str] = []

            async with client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    # Detect Anthropic Agent Skills invocations.
                    if (
                        _use_skills
                        and getattr(event, "type", None) == "content_block_start"
                        and getattr(getattr(event, "content_block", None), "type", None)
                        == "server_tool_use"
                    ):
                        skill_name = getattr(event.content_block, "name", "unknown")
                        server_tool_uses.append(skill_name)

                response = await stream.get_final_message()

            turn_ms = int((time.monotonic() - turn_start) * 1000)
            in_tok = response.usage.input_tokens
            out_tok = response.usage.output_tokens
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cache_write = getattr(response.usage, "cache_creation_input_tokens", 0) or 0

            step_cost = _compute_cost(model, in_tok, out_tok, cache_read, cache_write)
            total_cost += step_cost
            total_input += in_tok
            total_output += out_tok

            emit_model_turn_end(
                run_id=_run_id,
                step=step,
                tokens_input=in_tok,
                tokens_output=out_tok,
                cost_usd=step_cost,
                duration_ms=turn_ms,
                tokens_cache_read=cache_read or None,
                tokens_cache_write=cache_write or None,
            )
            emit_cost_update(
                run_id=_run_id,
                total_cost_usd=total_cost,
                total_tokens=total_input + total_output,
            )

            for block in response.content:
                if block.type == "text" and block.text.strip():
                    emit_text_output(run_id=_run_id, step=step, text=block.text)

            # Emit skill_execute for each Anthropic Skills invocation observed.
            for skill_name in server_tool_uses:
                emit_skill_execute(run_id=_run_id, step=step, name=skill_name)

            yield response

            if response.stop_reason == "max_tokens":
                stop_reason = "token_limit"
                break

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if response.stop_reason != "tool_use" or not tool_use_blocks:
                stop_reason = "converged"
                break

            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict] = []

            for tool_block in tool_use_blocks:
                call_id = tool_block.id
                tool_name = tool_block.name
                tool_input = tool_block.input

                emit_tool_call(
                    run_id=_run_id,
                    step=step,
                    call_id=call_id,
                    tool=tool_name,
                    input=tool_input,
                    subtype="function",
                )

                tool_start = time.monotonic()
                try:
                    if tool_name in _handlers:
                        raw = _handlers[tool_name](tool_input)
                        output = str(raw) if not isinstance(raw, str) else raw
                    else:
                        output = f"Unknown tool: {tool_name}"
                except Exception as exc:
                    output = f"Error executing {tool_name}: {exc}"

                tool_ms = int((time.monotonic() - tool_start) * 1000)

                emit_tool_result(
                    run_id=_run_id,
                    step=step,
                    call_id=call_id,
                    tool=tool_name,
                    output=output,
                    duration_ms=tool_ms,
                )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": output,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        else:
            stop_reason = "turn_limit"

    except Exception as exc:
        emit_error(run_id=_run_id, code="runner_crash", message=str(exc))
        stop_reason = "error"
        raise

    finally:
        duration_ms = int((time.monotonic() - run_start) * 1000)
        emit_agent_stop(
            run_id=_run_id,
            reason=stop_reason,
            total_tokens=total_input + total_output,
            total_cost_usd=total_cost,
            total_turns=step,
            duration_ms=duration_ms,
        )
