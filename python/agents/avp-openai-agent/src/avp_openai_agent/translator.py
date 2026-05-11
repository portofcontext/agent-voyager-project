"""OpenAIAgentTranslator — observer/translator that turns OpenAI Agents SDK
lifecycle callbacks into AVP v0.1 events.

Structurally parallel to `avp-claude-agent`: the OpenAI Agents SDK (PyPI
`openai-agents`, import `agents`) owns the agent loop, so we cannot drive
turns ourselves. We subclass `agents.RunHooks` and let the SDK call us:

  RunHooks.on_agent_start  → AVP `agent_started`
  RunHooks.on_agent_end    → AVP `agent_stopped` (final) or subagent return
  RunHooks.on_llm_start    → AVP `model_turn_started`
  RunHooks.on_llm_end      → AVP `model_turn_ended` + `cost_recorded`
                             + `text_emitted` (final assistant text) +
                             `reasoning_emitted` (per reasoning item)
  RunHooks.on_tool_start   → AVP `tool_invoked`
  RunHooks.on_tool_end     → AVP `tool_returned`
  RunHooks.on_handoff      → AVP `subagent_invoked`
                             (matching `on_agent_end` of the target →
                             `subagent_returned`)

Difference from `avp-claude-agent`: no cumulative-to-delta math. The
OpenAI Agents SDK passes the **just-completed LLM call's** usage on
`on_llm_end(response.usage)`, so each hook firing already carries the
per-turn delta. Cum-to-delta only enters the picture for SDKs that
report rolled-up usage on every message (Claude Agent SDK does this);
the OpenAI Agents SDK does not.

Commission → SDK options mapping is in `_build_agent`. Supervisors who
want SDK-only knobs (`temperature`, `tool_choice`, model settings, etc.)
pass them via `extra_run_config`; they pass through opaque to AVP.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
import warnings
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from avp import (
    ZERO_SPAN_ID,
    AgentDescribedData,
    AgentDescribedEvent,
    AgentDescriptor,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    Commission,
    CostRecordedData,
    CostRecordedEvent,
    ErrorOccurredData,
    ErrorOccurredEvent,
    ModelTurnEndedData,
    ModelTurnEndedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    ReasoningEmittedData,
    ReasoningEmittedEvent,
    RunRequestedData,
    RunRequestedEvent,
    RunStateSnapshot,
    StopReason,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentRef,
    SubagentReturnedData,
    SubagentReturnedEvent,
    TextEmittedData,
    TextEmittedEvent,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    new_span_id,
    new_trace_id,
)
from avp.enums import ErrorCode
from avp.types import now_iso

logger = logging.getLogger(__name__)

# ── Built-in tool catalog ─────────────────────────────────────────────────────
#
# Snapshot of the OpenAI-hosted tool classes shipped by `openai-agents` as of
# 2026-05-11. The SDK exposes these as constructable classes the supervisor
# selects via Commission.enabled_builtin_tools; we map each allowlisted name
# to its constructor at runtime in `_build_builtin_tools`.
#
# Source: openai/openai-agents-python (https://github.com/openai/openai-agents-python)
# Public: re-exported from `avp_openai_agent` so supervisors can filter the
# list when authoring `Commission.enabled_builtin_tools`.
OPENAI_AGENTS_SDK_BUILTIN_TOOLS: tuple[str, ...] = (
    "web_search",
    "file_search",
    "code_interpreter",
    "computer_use",
    "image_generation",
    "local_shell",
)


# ── Pricing ───────────────────────────────────────────────────────────────────
#
# Shared with avp-anthropic and avp-claude-agent via avp.pricing. Picks up
# the AVP_PRICES_PATH override automatically.

_DEFAULT_PRICES_CACHE: dict[str, Any] | None = None


def _default_prices() -> dict[str, Any]:
    global _DEFAULT_PRICES_CACHE
    if _DEFAULT_PRICES_CACHE is None:
        from avp import load_default_prices

        _DEFAULT_PRICES_CACHE = load_default_prices()
    return _DEFAULT_PRICES_CACHE


def _compute_cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_write: int,
) -> tuple[int, int, int, int, float, str]:
    """Return (tokens_input, tokens_output, cache_read, cache_write, cost_usd, cost_source).

    AVP convention: `tokens_input` INCLUDES cache reads. OpenAI's Responses
    API reports `prompt_tokens` already-inclusive of cached tokens plus a
    separate `cached_tokens` breakdown; we keep `tokens_input` inclusive
    and pass the cache portion to the shared `compute_cost` so the
    cache-read discount applies on the priced fraction. Models the price
    table doesn't know yield `(…, 0.0, "unknown")` plus a warning — silent
    under-counts are worse than a loud miss.
    """
    from avp import COST_SOURCE_UNKNOWN
    from avp import compute_cost as _shared_compute

    cost, source = _shared_compute(
        model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        prices=_default_prices(),
    )
    if source == COST_SOURCE_UNKNOWN:
        warnings.warn(
            f"avp-openai-agent: no price for model {model!r}; cost reported as 0.0",
            stacklevel=2,
        )
    return input_tokens, output_tokens, cache_read, cache_write, cost, source


def _monotonic_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _extract_usage(response: Any) -> tuple[int, int, int, int]:
    """Pull (input, output, cache_read, cache_write) from a ModelResponse.

    The OpenAI Agents SDK normalizes provider-specific usage into a
    `Usage` object (`agents.usage.Usage`) with `input_tokens`,
    `output_tokens`, `input_tokens_details.cached_tokens`. We defend
    against shape drift (older versions used different attribute names,
    fakes used dicts) by reading via attribute-then-dict-then-default.
    """
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return 0, 0, 0, 0

    def _get(obj: Any, *names: str, default: Any = 0) -> Any:
        for n in names:
            if obj is None:
                return default
            v = getattr(obj, n, None)
            if v is None and isinstance(obj, dict):
                v = obj.get(n)
            if v is not None:
                return v
        return default

    input_t = int(_get(usage, "input_tokens", "prompt_tokens") or 0)
    output_t = int(_get(usage, "output_tokens", "completion_tokens") or 0)
    details = _get(usage, "input_tokens_details", "prompt_tokens_details", default=None)
    cache_r = 0
    if details is not None:
        cache_r = int(_get(details, "cached_tokens") or 0)
    # OpenAI does not bill a separate cache-creation surcharge; writes are
    # billed at the standard input rate. cache_write stays 0.
    return input_t, output_t, cache_r, 0


def _classify_sdk_exception(e: Exception) -> ErrorCode:
    """Map an openai-agents / openai SDK exception to an AVP ErrorCode.

    Class-name matching avoids importing `openai` symbols at module top
    so `describe` and mock-only tests don't need the package installed.
    """
    type_name = type(e).__name__
    msg_lower = str(e).lower()

    if type_name == "RateLimitError" or "rate limit" in msg_lower or "429" in msg_lower:
        return ErrorCode.rate_limit
    if type_name in ("AuthenticationError", "PermissionDeniedError"):
        return ErrorCode.auth_error
    if any(
        phrase in msg_lower
        for phrase in (
            "invalid api key",
            "authentication failed",
            "unauthorized",
            "incorrect api key",
            "401",
            "403",
        )
    ):
        return ErrorCode.auth_error
    if any(
        phrase in msg_lower
        for phrase in (
            "context length",
            "context_length_exceeded",
            "maximum context length",
            "input is too long",
            "context window",
        )
    ):
        return ErrorCode.context_limit
    if type_name in ("BadRequestError",) and "model" in msg_lower and "not found" in msg_lower:
        return ErrorCode.unsupported_model
    return ErrorCode.agent_crash


def _provider_from_env() -> str:
    """Resolve `gen_ai.provider.name` for the OpenAI Agents SDK runtime.

    The SDK speaks the OpenAI API by default. Compatible third-party
    backends (Azure OpenAI, OpenRouter, Together, local Ollama, etc.) are
    selected by overriding the `OPENAI_BASE_URL` env var or passing a
    custom client. We tag accordingly so consumers can answer "which
    backend served this run." Conservative: only `azure.openai` and the
    `openai` default are auto-detected; everything else is reported
    `openai-compatible` rather than guessed.
    """
    import os

    base_url = (
        os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE") or ""
    ).lower()
    if not base_url or "api.openai.com" in base_url:
        return "openai"
    if "openai.azure.com" in base_url or "azure" in base_url:
        return "azure.openai"
    return "openai-compatible"


class OpenAIAgentTranslator:
    """Translates an OpenAI Agents SDK run into AVP v0.1 events.

    Construct with a Commission and an `on_event` callback that receives
    each emitted AVP event (Pydantic model). Call `.run()` to start the
    SDK; events fire as the SDK progresses.

    Optional `agent_factory` / `runner` injection points let tests
    substitute fakes without installing `openai-agents`. `agent_factory`
    is a zero-arg callable returning the `agents.Agent` to run;
    `runner` is an object with an async `run(agent, input, *, hooks,
    **kwargs)` method matching `agents.Runner`.
    """

    def __init__(
        self,
        commission: Commission,
        on_event: Callable[[BaseModel], None],
        *,
        descriptor: AgentDescriptor | None = None,
        agent_factory: Callable[[], Any] | None = None,
        runner: Any | None = None,
        parent_trace_id: str | None = None,
        parent_agent_span_id: str | None = None,
        suppress_lifecycle: bool = False,
        parent_tracer: Any | None = None,
        extra_run_config: dict[str, Any] | None = None,
    ) -> None:
        """Translate an OpenAI Agents SDK run into AVP events.

        `parent_trace_id` / `parent_agent_span_id` / `suppress_lifecycle`
        opt this translator into "delegated" mode — used by
        `traced_openai_runner()` when an outer `AVPTracer` is already
        managing the run.

        `extra_run_config` is a dict merged into the `RunConfig` passed
        to `Runner.run`. Use it for SDK-specific concerns that don't
        belong on the AVP wire (e.g., `tracing_disabled`,
        `model_settings`). Commission-level fields take precedence.
        """
        self.commission = commission
        self.on_event = on_event
        self._descriptor = descriptor
        self._agent_factory = agent_factory
        self._runner = runner
        self._extra_run_config = dict(extra_run_config or {})
        self._prelude_emitted = False
        self._call_seq = itertools.count(1)
        self._sa_seq = itertools.count(1)
        self._step = 0
        self._started_at = now_iso()
        self._started_monotonic_ms = _monotonic_ms()
        self._trace_id = parent_trace_id or new_trace_id()
        self._agent_span_id = parent_agent_span_id or new_span_id()
        self._suppress_lifecycle = suppress_lifecycle
        self._parent_tracer = parent_tracer
        # Per-turn state. RunHooks fires on_llm_start before each LLM
        # call and on_llm_end after; we hold the span between calls.
        self._current_turn_span_id: str | None = None
        self._turn_t0_monotonic_ms: int | None = None
        self._turn_open = False
        # Per-tool state, keyed by a synthetic call_id we mint at
        # on_tool_start because the Agents SDK's RunHooks surface does
        # not include the upstream tool_call_id.
        self._tool_stack: list[dict[str, Any]] = []
        # Handoff bookkeeping. `on_handoff(from, to)` opens an invocation;
        # the next `on_agent_end(to, output)` closes it. We track the most
        # recent open handoff per target-agent-name.
        self._subagents_by_name: dict[str, SubagentRef] = {
            sa.id: sa for sa in (commission.subagents or [])
        }
        self._open_handoffs: dict[str, dict[str, Any]] = {}
        # The "root" agent is the one we built from the Commission. Its
        # on_agent_end emits agent_stopped; handoff-target agents' ends
        # emit subagent_returned.
        self._root_agent_name: str | None = None
        # Running totals for the snapshot on agent_stopped.
        self._total_turns = 0
        self._total_cost_usd = 0.0
        self._total_tokens = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cache_read = 0
        self._total_cache_write = 0
        self._tools_invoked: dict[str, int] = {}
        self._agent_started_emitted = False
        # Stash the SDK's final RunResult so run() can extract the
        # terminal output and stop reason after the loop exits.
        self._final_result: Any | None = None

    # ── Snapshot ────────────────────────────────────────────────────────────

    def _snapshot(self) -> RunStateSnapshot:
        return RunStateSnapshot(
            total_cost_usd=self._total_cost_usd,
            total_tokens=self._total_tokens,
            total_turns=self._total_turns,
            tokens_input_total=self._total_input_tokens or None,
            tokens_output_total=self._total_output_tokens or None,
            tokens_cache_read_total=self._total_cache_read or None,
            tokens_cache_write_total=self._total_cache_write or None,
            tools_invoked=dict(self._tools_invoked) or None,
            started_at=self._started_at,
            duration_ms=max(0, _monotonic_ms() - self._started_monotonic_ms),
        )

    def _emit(self, event: BaseModel) -> None:
        self.on_event(event)

    # ── Span helpers ────────────────────────────────────────────────────────

    def _own_span(self, parent_span_id: str) -> dict[str, str]:
        return {
            "trace_id": self._trace_id,
            "span_id": new_span_id(),
            "parent_span_id": parent_span_id,
        }

    def _shared_span(self, span_id: str, parent_span_id: str) -> dict[str, str]:
        return {
            "trace_id": self._trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
        }

    def _current_parent_for_run_event(self) -> str:
        return self._current_turn_span_id or self._agent_span_id

    # ── Public lifecycle ────────────────────────────────────────────────────

    def run(self) -> AgentStoppedEvent | None:
        """Start the OpenAI Agents SDK run and emit AVP events as it progresses.

        Returns the terminal AgentStoppedEvent (or None in delegated mode,
        where the parent tracer emits the bookends).
        """
        self._emit_run_prelude()

        reason: StopReason
        error_msg: str | None = None
        try:
            asyncio.run(self._async_invoke_sdk())
            reason = self._reason_from_result(self._final_result)
        except KeyboardInterrupt:
            if not self._agent_started_emitted:
                self._emit_agent_started()
            reason = StopReason.interrupted
        except Exception as e:
            logger.exception("avp-openai-agent: SDK error")
            if not self._agent_started_emitted:
                self._emit_agent_started()
            classified_code = _classify_sdk_exception(e)
            self._emit(
                ErrorOccurredEvent(
                    subject=self.commission.run_id,
                    data=ErrorOccurredData(
                        **self._own_span(self._current_parent_for_run_event()),
                        **{
                            "avp.error.code": classified_code,
                            "avp.error.message": str(e),
                        },
                    ),
                )
            )
            reason = StopReason.error
            error_msg = str(e)
        finally:
            if self._turn_open:
                # Model was mid-turn — close it so the trajectory is
                # well-formed (lifecycle invariant: every turn_started
                # has a matching turn_ended).
                assert self._current_turn_span_id is not None
                self._emit(
                    ModelTurnEndedEvent(
                        subject=self.commission.run_id,
                        data=ModelTurnEndedData(
                            **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                            step=self._step,
                            duration_ms=0,
                            **{
                                "gen_ai.usage.input_tokens": 0,
                                "gen_ai.usage.output_tokens": 0,
                                "avp.cost_usd": 0.0,
                            },
                        ),
                    )
                )
                self._turn_open = False

        return self._emit_agent_stopped(reason, error_msg=error_msg)

    def _reason_from_result(self, result: Any) -> StopReason:
        """Map an `agents.RunResult` to a StopReason.

        The Agents SDK doesn't classify run outcomes; we infer:
          - guardrail-trip → refused
          - exception path (handled in run()) → error
          - everything else → converged
        """
        if result is None:
            # Run never produced a result (probably because exception path
            # already ran). Caller's branch decides; default to converged.
            return StopReason.converged
        # The SDK raises `InputGuardrailTripwireTriggered` /
        # `OutputGuardrailTripwireTriggered` as exceptions, not as result
        # state, so they land on the exception path (mapped to `error`).
        # Refusals from the model itself surface as content; v0.1 does not
        # try to detect them heuristically — converged is honest.
        return StopReason.converged

    # ── SDK integration ────────────────────────────────────────────────────

    async def _async_invoke_sdk(self) -> None:
        """Drive the OpenAI Agents SDK via Runner.run.

        Uses async `Runner.run` (rather than `run_sync`) because we're
        already inside asyncio.run. The SDK owns the loop; we observe.
        """
        if self._runner is None:
            from agents import Runner  # type: ignore[import-not-found]

            self._runner = Runner
        if self._agent_factory is None:
            self._agent_factory = self._default_agent_factory

        agent = self._agent_factory()
        self._root_agent_name = getattr(agent, "name", None) or "agent"

        hooks = _AVPRunHooks(self)
        prompt = self.commission.prompt or ""

        run_kwargs: dict[str, Any] = {"hooks": hooks}
        # Commission.model is enforced via the Agent's `model` attribute
        # at build time. extra_run_config covers everything else.
        run_kwargs.update(self._extra_run_config)

        self._final_result = await self._runner.run(agent, prompt, **run_kwargs)

    def _default_agent_factory(self) -> Any:
        """Build an `agents.Agent` from the Commission.

        Maps:
          - commission.prompt is the user input (passed to Runner.run,
            not the agent constructor).
          - commission.system_prompt → Agent.instructions
          - commission.model → Agent.model
          - commission.enabled_builtin_tools → Agent.tools (OpenAI-hosted
            tool classes from the Agents SDK).
          - commission.subagents → Agent.handoffs (each declared subagent
            becomes a handoff target; the Resolver-loaded body is the
            target Agent's instructions).
        """
        from agents import Agent  # type: ignore[import-not-found]

        commission = self.commission
        tools = self._build_builtin_tools(commission.enabled_builtin_tools)
        handoffs = self._build_handoffs()

        agent_kwargs: dict[str, Any] = {
            "name": "avp-agent",
            "instructions": commission.system_prompt or "",
            "tools": tools,
            "handoffs": handoffs,
        }
        if commission.model:
            agent_kwargs["model"] = commission.model
        return Agent(**agent_kwargs)

    def _build_builtin_tools(self, allow: Sequence[str] | None) -> list[Any]:
        """Construct the SDK's hosted-tool instances the Commission permits.

        Returns an empty list when the SDK isn't installed at constructor
        time (defensive — tests cover the builder shape without the SDK).
        Unrecognized names in the allowlist warn and are dropped.
        """
        if allow is None:
            return []
        try:
            from agents import (  # type: ignore[import-not-found]
                CodeInterpreterTool,
                ComputerTool,
                FileSearchTool,
                ImageGenerationTool,
                LocalShellTool,
                WebSearchTool,
            )
        except ImportError:
            return []
        registry: dict[str, Callable[[], Any]] = {
            "web_search": WebSearchTool,
            "file_search": FileSearchTool,
            "code_interpreter": CodeInterpreterTool,
            "computer_use": ComputerTool,
            "image_generation": ImageGenerationTool,
            "local_shell": LocalShellTool,
        }
        tools: list[Any] = []
        for name in allow:
            ctor = registry.get(name)
            if ctor is None:
                warnings.warn(
                    f"avp-openai-agent: unknown builtin tool {name!r}; dropping",
                    stacklevel=2,
                )
                continue
            try:
                tools.append(ctor())
            except Exception as e:  # pragma: no cover — defensive
                warnings.warn(
                    f"avp-openai-agent: failed to construct {name!r}: {e}",
                    stacklevel=2,
                )
        return tools

    def _build_handoffs(self) -> list[Any]:
        """Materialize Commission.subagents as handoff targets.

        v0.1 refs-only: each `SubagentRef` becomes an Agent with the ref's
        id as name and empty instructions (the resolver materializes the
        body in a future cut). The handoff itself opens a `subagent_*`
        frame in our hook callbacks — what the target agent actually does
        on the wire is its on_llm_start/end pairs, parented to the frame.
        """
        if not self.commission.subagents:
            return []
        try:
            from agents import Agent  # type: ignore[import-not-found]
        except ImportError:
            return []
        targets: list[Any] = []
        for sa in self.commission.subagents:
            targets.append(
                Agent(
                    name=sa.id,
                    # Placeholder. Future: load via resolver.
                    instructions=f"Subagent {sa.id} (handoff target).",
                )
            )
        return targets

    # ── RunHooks callbacks ─────────────────────────────────────────────────
    #
    # These are async methods called from the SDK's run loop. Each maps to
    # one or two AVP events. RunHooks are observation-only — they cannot
    # modify SDK behavior.

    async def on_agent_start(self, context: Any, agent: Any) -> None:
        name = getattr(agent, "name", None) or "agent"
        if not self._agent_started_emitted and name == self._root_agent_name:
            self._emit_agent_started(agent=agent)
            return
        # Non-root start: this is a handoff target spinning up. The
        # subagent_invoked event was already emitted on on_handoff;
        # nothing to add here. (The target's on_llm_start/end pairs will
        # surface its turns, parented to the subagent frame span.)

    async def on_agent_end(self, context: Any, agent: Any, output: Any) -> None:
        name = getattr(agent, "name", None) or "agent"
        # Close any open handoff for this agent.
        frame = self._open_handoffs.pop(name, None)
        if frame is not None:
            self._emit_subagent_returned(frame=frame, output=output)
            return
        # Root agent end: defer agent_stopped to run() so it sees the
        # final RunResult and can classify the reason from any error
        # surfaced post-loop.

    async def on_llm_start(
        self, context: Any, agent: Any, system_prompt: Any, input_items: Any
    ) -> None:
        self._step += 1
        self._current_turn_span_id = new_span_id()
        self._turn_t0_monotonic_ms = _monotonic_ms()
        # Parent the turn under the active subagent frame (if a handoff
        # is mid-flight) or the root agent span otherwise.
        parent = self._active_frame_span_id()
        self._emit(
            ModelTurnStartedEvent(
                subject=self.commission.run_id,
                data=ModelTurnStartedData(
                    **self._shared_span(self._current_turn_span_id, parent),
                    step=self._step,
                    # The Agents SDK uses streaming under the hood for
                    # Runner.run_streamed; Runner.run is non-streaming.
                    # We can't tell which from RunHooks alone, so we
                    # report False — conservative honest.
                    **{"gen_ai.request.stream": False},
                ),
            )
        )
        self._turn_open = True

    async def on_llm_end(self, context: Any, agent: Any, response: Any) -> None:
        if self._current_turn_span_id is None:
            # on_llm_end without a matching start — shouldn't happen, but
            # the SDK is moving; bail rather than crash.
            return
        commission = self.commission
        model_id = (
            getattr(response, "model", None)
            or getattr(agent, "model", None)
            or commission.model
            or "unknown"
        )

        input_t, output_t, cache_r, cache_w = _extract_usage(response)
        _, _, _, _, cost, cost_source = _compute_cost(
            str(model_id),
            input_tokens=input_t,
            output_tokens=output_t,
            cache_read=cache_r,
            cache_write=cache_w,
        )

        # Text + reasoning blocks. The Agents SDK exposes `response.output`
        # as a list of typed items (ResponseOutputMessage, ReasoningItem,
        # ToolCallItem, ...) per the Responses API shape. We dispatch by
        # type name to stay decoupled from SDK internal classes.
        for item in self._iter_output_items(response):
            kind = type(item).__name__
            if kind in ("ResponseOutputMessage", "MessageOutputItem"):
                text = self._extract_message_text(item)
                if text:
                    self._emit(
                        TextEmittedEvent(
                            subject=commission.run_id,
                            data=TextEmittedData(
                                **self._own_span(self._current_turn_span_id),
                                step=self._step,
                                **{"avp.text": text},
                            ),
                        )
                    )
            elif kind in ("ReasoningItem", "ResponseReasoningItem"):
                text = self._extract_reasoning_text(item)
                self._emit(
                    ReasoningEmittedEvent(
                        subject=commission.run_id,
                        data=ReasoningEmittedData(
                            **self._own_span(self._current_turn_span_id),
                            step=self._step,
                            **{
                                "avp.reasoning.text": text or "",
                                "avp.reasoning.redacted": not bool(text),
                            },
                        ),
                    )
                )
            # ToolCallItem / HandoffCallItem are surfaced by RunHooks'
            # on_tool_start / on_handoff respectively; we don't double-emit
            # them here.

        ended_kwargs: dict[str, Any] = {
            "gen_ai.usage.input_tokens": input_t,
            "gen_ai.usage.output_tokens": output_t,
            "gen_ai.usage.cache_read.input_tokens": cache_r,
            "gen_ai.usage.cache_creation.input_tokens": cache_w,
            "avp.cost_usd": cost,
            "avp.cost.source": cost_source,
            "gen_ai.response.model": str(model_id),
        }
        finish_reasons = self._extract_finish_reasons(response)
        if finish_reasons:
            ended_kwargs["gen_ai.response.finish_reasons"] = finish_reasons

        turn_duration_ms = 0
        if self._turn_t0_monotonic_ms is not None:
            turn_duration_ms = max(0, _monotonic_ms() - self._turn_t0_monotonic_ms)
            self._turn_t0_monotonic_ms = None

        self._emit(
            ModelTurnEndedEvent(
                subject=commission.run_id,
                data=ModelTurnEndedData(
                    **self._shared_span(self._current_turn_span_id, self._active_frame_span_id()),
                    step=self._step,
                    duration_ms=turn_duration_ms,
                    **ended_kwargs,
                ),
            )
        )
        self._turn_open = False

        self._total_turns += 1
        self._total_cost_usd += cost
        self._total_tokens += input_t + output_t
        self._total_input_tokens += input_t
        self._total_output_tokens += output_t
        self._total_cache_read += cache_r
        self._total_cache_write += cache_w

        if self._parent_tracer is not None:
            self._parent_tracer.accumulate_external(
                tokens_input=input_t,
                tokens_output=output_t,
                cost_usd=cost,
                cache_read=cache_r,
                cache_write=cache_w,
            )

        self._emit(
            CostRecordedEvent(
                subject=commission.run_id,
                data=CostRecordedData(
                    **self._own_span(self._current_turn_span_id),
                    **{
                        "avp.state": self._snapshot(),
                        "avp.cost.source": cost_source,
                    },
                ),
            )
        )

    async def on_tool_start(self, context: Any, agent: Any, tool: Any) -> None:
        tool_name = getattr(tool, "name", None) or type(tool).__name__
        call_id = f"call-{next(self._call_seq)}"
        tool_span_id = new_span_id()
        self._tool_stack.append(
            {
                "call_id": call_id,
                "tool_name": tool_name,
                "tool_span_id": tool_span_id,
                "t0_monotonic_ms": _monotonic_ms(),
            }
        )
        parent = self._current_turn_span_id or self._active_frame_span_id()
        # Hosted-tool dispatch target: OpenAI runs web_search /
        # file_search / code_interpreter / computer_use / image_generation
        # on its own infrastructure. Local tools are user-defined function
        # tools the SDK invokes in-process.
        # AVP v0.1 only defines `mcp_server` / `local`. OpenAI-hosted tools
        # (web_search, file_search, code_interpreter, etc.) run on OpenAI's
        # infrastructure but the agent itself dispatches them, so `local`
        # is the honest tag — the AVP wire doesn't carry a `remote-hosted`
        # axis. Consumers cross-reference the descriptor's tool catalog
        # for "this is a hosted tool" semantics.
        dispatch = "local"
        self._emit(
            ToolInvokedEvent(
                subject=self.commission.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, parent),
                    step=self._step,
                    **{
                        "gen_ai.tool.call.id": call_id,
                        "gen_ai.tool.name": tool_name,
                        # The Agents SDK RunHooks surface does not carry
                        # the tool arguments. Emit an empty object; full
                        # arguments are recoverable via SDK tracing.
                        "gen_ai.tool.call.arguments": {},
                        "avp.tool.dispatch_target": dispatch,
                    },
                ),
            )
        )
        self._tools_invoked[tool_name] = self._tools_invoked.get(tool_name, 0) + 1

    async def on_tool_end(self, context: Any, agent: Any, tool: Any, result: Any) -> None:
        if not self._tool_stack:
            return
        frame = self._tool_stack.pop()
        tool_span_id: str = frame["tool_span_id"]
        call_id: str = frame["call_id"]
        tool_name: str = frame["tool_name"]
        duration_ms = max(0, _monotonic_ms() - frame["t0_monotonic_ms"])

        result_text, result_structured = _coerce_result(result)
        parent = self._current_turn_span_id or self._active_frame_span_id()
        returned_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": call_id,
            "gen_ai.tool.name": tool_name,
            "avp.tool.result.text": result_text,
        }
        if result_structured is not None:
            returned_kwargs["avp.tool.result.structured"] = result_structured
        self._emit(
            ToolReturnedEvent(
                subject=self.commission.run_id,
                data=ToolReturnedData(
                    **self._shared_span(tool_span_id, parent),
                    step=self._step,
                    duration_ms=duration_ms,
                    **returned_kwargs,
                ),
            )
        )

    async def on_handoff(self, context: Any, from_agent: Any, to_agent: Any) -> None:
        """A handoff transfers control from `from_agent` to `to_agent`. We
        treat it as a subagent invocation: emit `subagent_invoked` here,
        and emit `subagent_returned` on `on_agent_end` of `to_agent`.

        Note the semantic stretch: OpenAI handoffs are control-transfers,
        not function calls. The target agent doesn't return to the caller
        in the SDK's sense — it owns the run from that point on (or until
        another handoff). v0.1 of AVP only has subagent vocabulary for
        this pattern, so we use it; the wire stays frozen.
        """
        target_name = getattr(to_agent, "name", None) or "subagent"
        invocation_id = f"sa-{next(self._sa_seq)}"
        frame_span_id = new_span_id()
        parent = self._current_turn_span_id or self._agent_span_id
        self._open_handoffs[target_name] = {
            "invocation_id": invocation_id,
            "frame_span_id": frame_span_id,
            "t0_monotonic_ms": _monotonic_ms(),
            "sa_name": target_name,
        }
        # The handoff target's name doubles as the AVP subagent id; if the
        # Commission declared this as a SubagentRef the names line up by
        # construction (we built the handoff Agent from sa.id).
        sa_id = target_name
        self._emit(
            SubagentInvokedEvent(
                subject=self.commission.run_id,
                data=SubagentInvokedData(
                    **self._shared_span(frame_span_id, parent),
                    step=self._step,
                    **{
                        "gen_ai.agent.name": sa_id,
                        "avp.subagent.invocation_id": invocation_id,
                        # RunHooks doesn't surface the user-visible
                        # handoff input directly; pass an empty struct.
                        "avp.subagent.input": {},
                    },
                ),
            )
        )
        self._tools_invoked[sa_id] = self._tools_invoked.get(sa_id, 0) + 1

    def _emit_subagent_returned(self, *, frame: dict[str, Any], output: Any) -> None:
        result_text, result_structured = _coerce_result(output)
        duration_ms = max(0, _monotonic_ms() - frame["t0_monotonic_ms"])
        zero_usage = RunStateSnapshot(total_cost_usd=0.0, total_tokens=0, total_turns=0)
        returned_data: dict[str, Any] = {
            "step": self._step,
            "gen_ai.agent.name": frame["sa_name"],
            "avp.subagent.invocation_id": frame["invocation_id"],
            "duration_ms": duration_ms,
            "avp.subagent.result.text": result_text,
            "avp.subagent.reason": StopReason.converged,
            "avp.subagent.usage": zero_usage,
        }
        if result_structured is not None:
            returned_data["avp.subagent.result.structured"] = result_structured
        parent = self._current_turn_span_id or self._agent_span_id
        self._emit(
            SubagentReturnedEvent(
                subject=self.commission.run_id,
                data=SubagentReturnedData(
                    **self._shared_span(frame["frame_span_id"], parent),
                    **returned_data,
                ),
            )
        )

    # ── Span tree helpers ─────────────────────────────────────────────────

    def _active_frame_span_id(self) -> str:
        """The span_id model turns should parent under.

        If a handoff is open, use that subagent's frame span so the
        target's turns nest under the invocation. Otherwise the root
        agent span.
        """
        if self._open_handoffs:
            # Last-opened is the active one (handoffs are sequential, not
            # nested, in the Agents SDK).
            return next(reversed(self._open_handoffs.values()))["frame_span_id"]
        return self._agent_span_id

    # ── Output-item parsing (defensive, version-tolerant) ─────────────────

    def _iter_output_items(self, response: Any) -> list[Any]:
        out = getattr(response, "output", None)
        if out is None and isinstance(response, dict):
            out = response.get("output")
        if not out:
            return []
        if not isinstance(out, list):
            return []
        return out

    def _extract_message_text(self, item: Any) -> str:
        """Pull the assistant's text content out of a message-output item.

        OpenAI Responses API messages carry `content: list[ContentBlock]`
        where each block has a `type` and either `.text` (for output_text)
        or a nested representation. We concatenate all text-bearing blocks.
        """
        content = getattr(item, "content", None)
        if content is None and isinstance(item, dict):
            content = item.get("content")
        if not content:
            return ""
        parts: list[str] = []
        if isinstance(content, str):
            return content
        for block in content:
            text = (
                getattr(block, "text", None)
                or (block.get("text") if isinstance(block, dict) else None)
                or ""
            )
            if text:
                parts.append(str(text))
        return "".join(parts)

    def _extract_reasoning_text(self, item: Any) -> str:
        """Pull reasoning summary out of a reasoning-output item.

        Responses-API reasoning items carry summary text on `.summary`
        as a list of `Summary` blocks each with `.text`; older shapes use
        `.content` or `.text` directly.
        """
        summary = getattr(item, "summary", None)
        if summary is None and isinstance(item, dict):
            summary = item.get("summary")
        if summary:
            parts: list[str] = []
            for s in summary:
                text = (
                    getattr(s, "text", None)
                    or (s.get("text") if isinstance(s, dict) else None)
                    or ""
                )
                if text:
                    parts.append(str(text))
            if parts:
                return "".join(parts)
        # Fall back to .text on the item itself.
        return str(getattr(item, "text", "") or "")

    def _extract_finish_reasons(self, response: Any) -> list[str] | None:
        # The Responses API doesn't expose `finish_reason` the way Chat
        # Completions does; `response.status` ("completed", "incomplete",
        # "failed") is the closest analog. Pass through as a list of one
        # so the OTel-shape stays consistent with the Anthropic agent.
        status = getattr(response, "status", None)
        if status is None and isinstance(response, dict):
            status = response.get("status")
        if status:
            return [str(status)]
        return None

    # ── Emission helpers ──────────────────────────────────────────────────

    def _emit_run_prelude(self) -> None:
        if self._suppress_lifecycle or self._descriptor is None or self._prelude_emitted:
            return
        commission = self.commission
        sup = commission.supervisor
        commission_snapshot = commission.model_dump(by_alias=True, exclude_none=True, mode="json")
        run_requested_kwargs: dict[str, Any] = {
            "avp.supervisor.name": sup.name if sup is not None else "unknown",
            "avp.commission": commission_snapshot,
        }
        if sup is not None and sup.version is not None:
            run_requested_kwargs["avp.supervisor.version"] = sup.version
        self._emit(
            RunRequestedEvent(
                subject=commission.run_id,
                data=RunRequestedData(
                    trace_id=self._trace_id,
                    span_id=new_span_id(),
                    parent_span_id=ZERO_SPAN_ID,
                    **run_requested_kwargs,
                ),
            )
        )
        self._emit(
            AgentDescribedEvent(
                subject=commission.run_id,
                data=AgentDescribedData(
                    trace_id=self._trace_id,
                    span_id=new_span_id(),
                    parent_span_id=ZERO_SPAN_ID,
                    **{"avp.descriptor": self._descriptor},
                ),
            )
        )
        self._prelude_emitted = True

    def _emit_agent_started(self, *, agent: Any | None = None) -> None:
        """Emit `agent_started` carrying the resolved tool / subagent surface.

        Called from RunHooks.on_agent_start (root agent) so the event
        carries the SDK-side enrichment (the Agent's actual configured
        tools / handoffs) rather than commission-only stubs.
        """
        if self._suppress_lifecycle or self._agent_started_emitted:
            return
        commission = self.commission

        # Tool surface. Pulls names off the Agent's `tools` list if the
        # SDK gave us an agent; falls back to Commission allowlist + the
        # bundled built-in catalog otherwise.
        tools_meta: list[dict[str, Any]] | None = None
        if agent is not None and getattr(agent, "tools", None):
            tools_meta = []
            for t in agent.tools:
                name = getattr(t, "name", None) or type(t).__name__
                tools_meta.append({"name": name, "avp.dispatch_target": "local"})
        elif commission.enabled_builtin_tools is not None:
            tools_meta = [
                {"name": n, "avp.dispatch_target": "local"}
                for n in commission.enabled_builtin_tools
                if n in OPENAI_AGENTS_SDK_BUILTIN_TOOLS
            ] or None

        # Subagent surface from Commission refs. Handoff targets the SDK
        # actually configured show up on agent_started too if we can
        # introspect them.
        subagents_meta: list[dict[str, Any]] | None = None
        if commission.subagents:
            subagents_meta = [{"name": sa.id} for sa in commission.subagents]

        data_kwargs: dict[str, Any] = {
            "trace_id": self._trace_id,
            "span_id": self._agent_span_id,
            "parent_span_id": ZERO_SPAN_ID,
            "prompt": commission.prompt,
            "system_prompt": commission.system_prompt,
            "tools": tools_meta,
            "skills": None,
            "subagents": subagents_meta,
        }
        if commission.model:
            data_kwargs["gen_ai.request.model"] = commission.model
        data_kwargs["gen_ai.operation.name"] = "invoke_agent"
        data_kwargs["gen_ai.provider.name"] = _provider_from_env()
        if commission.thread_id:
            data_kwargs["avp.thread_id"] = commission.thread_id
        if commission.tags:
            data_kwargs["avp.tags"] = commission.tags
        if commission.meta:
            data_kwargs["avp.meta"] = commission.meta
        self._emit(
            AgentStartedEvent(
                subject=commission.run_id,
                data=AgentStartedData(**data_kwargs),
            )
        )
        self._agent_started_emitted = True

    def _emit_agent_stopped(
        self, reason: StopReason, *, error_msg: str | None = None
    ) -> AgentStoppedEvent | None:
        if self._suppress_lifecycle:
            return None
        snap = self._snapshot()
        ev = AgentStoppedEvent(
            subject=self.commission.run_id,
            data=AgentStoppedData(
                trace_id=self._trace_id,
                span_id=self._agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                **{
                    "avp.reason": reason,
                    "avp.state": snap,
                    "avp.total_tokens": snap.total_tokens,
                    "avp.total_cost_usd": snap.total_cost_usd,
                    "avp.total_turns": snap.total_turns,
                    "avp.duration_ms": snap.duration_ms,
                },
            ),
        )
        self._emit(ev)
        return ev


def _coerce_result(value: Any) -> tuple[str, Any | None]:
    """Coerce a tool / handoff result into (text, structured-or-None).

    Strings pass through as text with no structured form. Anything else
    is JSON-encoded if possible; failing that, we stringify. Matches
    the convention `avp-claude-agent` uses for tool outputs.
    """
    if isinstance(value, str):
        return value, None
    try:
        return json.dumps(value), value
    except (TypeError, ValueError):
        return str(value), None


class _AVPRunHooks:
    """Adapter from `agents.RunHooks` to OpenAIAgentTranslator.

    Constructed inline so we can lazy-import `agents.RunHooks` only when
    the SDK is actually installed (tests can construct the translator
    without the SDK present). At call time we dynamically inherit from
    `RunHooks` to ensure we satisfy any isinstance() checks in the SDK.
    """

    def __new__(cls, translator: OpenAIAgentTranslator) -> Any:
        try:
            from agents import RunHooks  # type: ignore[import-not-found]
        except ImportError:
            base: type = object
        else:
            base = RunHooks

        class _Bound(base):  # type: ignore[misc, valid-type]
            def __init__(self, t: OpenAIAgentTranslator) -> None:
                if base is not object:
                    # Some RunHooks versions have a no-arg __init__; others
                    # are pure protocol with no __init__. Suppress the TypeError
                    # so we work against either shape.
                    with contextlib.suppress(TypeError):
                        super().__init__()
                self._t = t

            async def on_agent_start(self, context: Any, agent: Any) -> None:
                await self._t.on_agent_start(context, agent)

            async def on_agent_end(self, context: Any, agent: Any, output: Any) -> None:
                await self._t.on_agent_end(context, agent, output)

            async def on_llm_start(
                self,
                context: Any,
                agent: Any,
                system_prompt: Any,
                input_items: Any,
            ) -> None:
                await self._t.on_llm_start(context, agent, system_prompt, input_items)

            async def on_llm_end(self, context: Any, agent: Any, response: Any) -> None:
                await self._t.on_llm_end(context, agent, response)

            async def on_tool_start(self, context: Any, agent: Any, tool: Any) -> None:
                await self._t.on_tool_start(context, agent, tool)

            async def on_tool_end(self, context: Any, agent: Any, tool: Any, result: Any) -> None:
                await self._t.on_tool_end(context, agent, tool, result)

            async def on_handoff(self, context: Any, from_agent: Any, to_agent: Any) -> None:
                await self._t.on_handoff(context, from_agent, to_agent)

        return _Bound(translator)
