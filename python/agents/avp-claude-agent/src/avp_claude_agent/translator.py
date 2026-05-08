"""ClaudeAgentTranslator — observer/translator that turns Claude Agent SDK
lifecycle events into AVP v0.1 events.

Structurally different from avp-anthropic's driver pattern: the Claude Agent
SDK owns the agent loop, so we cannot drive turns ourselves. Instead, we wire
into the SDK's two natural observation surfaces:

  1. The async message stream from `query()` — delivers AssistantMessage
     (one per model call) and ResultMessage (final usage). We emit
     model_turn_started/ended, text_emitted, and cost_recorded from these.
  2. Claude Code hooks — registered through ClaudeAgentOptions.hooks.
     PreToolUse fires before each tool invocation; PostToolUse fires after.
     We emit tool_invoked / tool_returned from these. Hooks return `{}` to
     pass through (no-op observability — we observe, we don't gate).

Commission → SDK options mapping is in `_build_sdk_options`. The supervisor's
`allowed_tools` is enforced natively by the SDK via ClaudeAgentOptions.
v0.1 leaves bounded execution to the caller (no max_turns / max_budget_usd
mapping) — agents that need it wire it externally.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from avp import (
    ZERO_SPAN_ID,
    AgentDescribedData,
    AgentDescribedEvent,
    AgentManifest,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    Commission,
    CostRecordedData,
    CostRecordedEvent,
    ErrorOccurredData,
    ErrorOccurredEvent,
    McpServerConnectedData,
    McpServerConnectedEvent,
    ModelTurnEndedData,
    ModelTurnEndedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    ReasoningEmittedData,
    ReasoningEmittedEvent,
    RunRequestedData,
    RunRequestedEvent,
    RunStateSnapshot,
    Source,
    StopReason,
    Subagent,
    SubagentInvokedData,
    SubagentInvokedEvent,
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

# MCP protocol version we declare on `mcp_server_connected` events. Same
# value the AVP reference agent uses; tracks the upstream MCP spec.
MCP_PROTOCOL_VERSION = "2025-11-25"

logger = logging.getLogger(__name__)


# ── Pricing ───────────────────────────────────────────────────────────────────
#
# Loads from `avp.pricing` (shared across agent packages) so a single
# table change covers both. `cost_source` rides alongside the cost number
# on the wire under `avp.cost.source`.


_DEFAULT_PRICES_CACHE: dict[str, Any] | None = None


def _default_prices() -> dict[str, Any]:
    global _DEFAULT_PRICES_CACHE
    if _DEFAULT_PRICES_CACHE is None:
        from avp import load_default_prices

        _DEFAULT_PRICES_CACHE = load_default_prices()
    return _DEFAULT_PRICES_CACHE


def _compute_cost(
    model: str, usage: dict[str, Any] | None
) -> tuple[int, int, int, int, float, str]:
    """Return (tokens_input, tokens_output, cache_read, cache_write, cost_usd, cost_source).

    AVP convention: tokens_input INCLUDES cache reads. Anthropic reports the
    fresh-only number, so we add cache reads/writes back. `cost_source` is
    "computed" when we got it from the price table, "unknown" when the
    model is missing — caller stamps it on `avp.cost.source` so audit
    consumers can tell trusted numbers from gap-fills."""
    if not usage:
        return 0, 0, 0, 0, 0.0, "computed"
    input_t = int(usage.get("input_tokens", 0) or 0)
    output_t = int(usage.get("output_tokens", 0) or 0)
    cache_r = int(usage.get("cache_read_input_tokens", 0) or 0)
    cache_w = int(usage.get("cache_creation_input_tokens", 0) or 0)
    avp_input = input_t + cache_r + cache_w

    from avp import COST_SOURCE_UNKNOWN
    from avp import compute_cost as _shared_compute

    cost, source = _shared_compute(
        model,
        input_tokens=avp_input,
        output_tokens=output_t,
        cache_read=cache_r,
        cache_write=cache_w,
        prices=_default_prices(),
    )
    if source == COST_SOURCE_UNKNOWN:
        warnings.warn(
            f"avp-claude-agent: no price for model {model!r}; cost reported as 0.0", stacklevel=2
        )
    return avp_input, output_t, cache_r, cache_w, cost, source


def _monotonic_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


# Built-in subagents the Claude Agent SDK runtime always makes available
# regardless of what the supervisor declares in `Commission.subagents`. Per
# the SDK subagents docs, `general-purpose` is the ONLY SDK-bundled
# subagent — `Explore` and `Plan` (mentioned in the Claude Code permissions
# docs) are filesystem-discovered from `.claude/agents/`, not runtime-bundled.
# The Python SDK doesn't ship a programmatic catalog; we snapshot from the
# documented surface.
#
# Source: https://code.claude.com/docs/en/agent-sdk/subagents
#   "Built-in general-purpose: Claude can invoke the built-in
#   `general-purpose` subagent at any time via the Agent tool without
#   you defining anything"
# Snapshot: 2026-05-08. Update if the SDK ships additional bundled subagents.
#
# Public: re-exported from `avp_claude_agent` so Commission authors can
# `from avp_claude_agent import CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS` and
# include / exclude these names from their `Commission.subagents` deliberately.
CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS: tuple[str, ...] = ("general-purpose",)
# Backwards-compat alias for the existing private callers in this module.
_CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS = CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS

# NOTE on skills: the Claude Agent SDK does NOT bundle skills programmatically.
# Per https://code.claude.com/docs/en/agent-sdk/skills:
#   "Unlike subagents (which can be defined programmatically), Skills must
#   be created as filesystem artifacts. The SDK does not provide a
#   programmatic API for registering Skills."
# Skills are discovered from `~/.claude/skills/`, project `.claude/skills/`,
# and plugin paths at runtime — that surface is environment-specific and
# not enumerable from translation time. So `agent_started.data.skills`
# stays `cfg.skills` only; we don't snapshot a "default skill list."
# Bundled skills mentioned in Claude Code docs (`/simplify`, `/debug`, etc.)
# are CLI features, not runtime-loaded artifacts the Python SDK exposes.


# Canonical list of tools the Claude Agent SDK's `claude_code` preset
# exposes when `ClaudeAgentOptions.tools` is left at default (None). The
# SDK delegates to the Claude Code CLI binary which owns the actual list;
# the Python SDK does NOT expose it programmatically. We snapshot from
# the public Claude Code documentation so a worker that doesn't restrict
# tools (the most common shape) still gets a usable
# `agent_started.data.tools` audit on the wire.
#
# Sources:
#   https://code.claude.com/docs/en/permissions
#   https://code.claude.com/docs/en/settings
# Snapshot: 2026-05-08. Update when Claude Code ships new built-ins.
#
# We omit `PowerShell` (gated behind CLAUDE_CODE_USE_POWERSHELL_TOOL=1)
# and the `Agent` / `EnterWorktree` tools (subagent / worktree management
# are surfaced via the dedicated subagent_invoked / worktree events).
#
# Public: re-exported from `avp_claude_agent` so Commission authors can
# `from avp_claude_agent import CLAUDE_CODE_PRESET_TOOLS` and pass or
# filter the list when building `Commission.allowed_tools`.
CLAUDE_CODE_PRESET_TOOLS: tuple[str, ...] = (
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "WebFetch",
    "WebSearch",
    "Task",
    "TodoWrite",
    "NotebookEdit",
)
# Backwards-compat alias for existing private callers.
_CLAUDE_CODE_PRESET_TOOLS = CLAUDE_CODE_PRESET_TOOLS


def _make_builtin_tool_decl(name: str) -> dict[str, Any]:
    """Build a `_ToolDecl`-shaped dict for one SDK-side tool name surfaced
    on `agent_started.data.tools`.

    The Claude Agent SDK does NOT expose its built-in tool catalog
    (Read, Write, Bash, Edit, Glob, Grep, …) programmatically — the
    canonical descriptions live in the Claude Code CLI binary and
    Anthropic's docs, not in the Python SDK. Rather than ship a
    hardcoded prose table that drifts the moment Anthropic ships a new
    tool or renames an existing one, we emit just `name` +
    `avp.dispatch_target` here and let consumers cross-reference Claude
    Code's tool documentation when they need descriptions.

    For `mcp__<server>__<tool>` names the SDK uses for MCP-routed tools,
    tag `dispatch_target=mcp_server` + `avp.mcp_server_id` so consumers
    can correlate with `mcp_server_connected` events. Everything else
    is `local` (the SDK runs it in-process); those are inspected via
    PreToolUse / PostToolUse hooks at dispatch time, where the SDK
    surfaces real input/output we DO record on the wire.
    """
    if name.startswith("mcp__"):
        rest = name[len("mcp__") :]
        idx = rest.find("__")
        if idx > 0:
            return {
                "name": name,
                "avp.dispatch_target": "mcp_server",
                "avp.mcp_server_id": rest[:idx],
            }
    return {"name": name, "avp.dispatch_target": "local"}


def _provider_from_env() -> str:
    """Resolve `gen_ai.provider.name` for the Claude Agent SDK runtime.

    The SDK speaks the Anthropic API on the wire — that's what `gen_ai.provider.name`
    reflects. The actual backend is selected at SDK invocation via these
    environment variables (mutually exclusive with each other, all default
    off):

      - `CLAUDE_CODE_USE_BEDROCK=1`  → AWS Bedrock serves the request
      - `CLAUDE_CODE_USE_VERTEX=1`   → Google Vertex AI serves the request
      - `CLAUDE_CODE_USE_FOUNDRY=1`  → Microsoft Foundry / Azure AI serves the request

    With none set, the SDK calls Anthropic directly. We tag accordingly so a
    supervisor reading the trajectory can answer "which cloud actually served
    this run" — the most useful provenance question for billing, latency, and
    regional analysis.

    What we do NOT do (and the previous version did): infer the provider from
    the model name. That was wrong. The SDK is Claude-only natively; non-Claude
    via LiteLLM proxy still speaks Anthropic on the wire and has nothing to do
    with the model-name prefix. A model id like `bedrock-claude-sonnet-4` does
    not imply Bedrock — the env var does.
    """
    import os

    if os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1":
        return "aws.bedrock"
    if os.environ.get("CLAUDE_CODE_USE_VERTEX") == "1":
        return "gcp.vertex_ai"
    if os.environ.get("CLAUDE_CODE_USE_FOUNDRY") == "1":
        return "azure.ai.inference"
    return "anthropic"


class ClaudeAgentTranslator:
    """Translates a Claude Agent SDK run into AVP v0.1 events.

    Construct with a Commission and an `on_event` callback that receives each
    emitted AVP event (Pydantic model). Call .run() to start the SDK; events
    fire as the SDK progresses.

    Optional `sdk_client_cls` / `sdk_options_cls` / `sdk_hook_matcher_cls`
    injection points let tests (and the supervisor's mock-SDK example) substitute
    fakes without installing claude_agent_sdk. `sdk_client_cls` is a callable
    that returns an object with the ClaudeSDKClient surface
    (`async with`-able, `connect()`, `query()`, `receive_response()`).
    """

    def __init__(
        self,
        config: Commission,
        on_event: Callable[[BaseModel], None],
        *,
        manifest: AgentManifest | None = None,
        local_tools: Any | None = None,
        local_tools_server_name: str = "local",
        sdk_client_cls: Callable[..., Any] | None = None,
        sdk_options_cls: type | None = None,
        sdk_hook_matcher_cls: type | None = None,
        sdk_agent_definition_cls: type | None = None,
        parent_trace_id: str | None = None,
        parent_agent_span_id: str | None = None,
        suppress_lifecycle: bool = False,
        parent_tracer: Any | None = None,
    ) -> None:
        """Translates Claude Agent SDK events to AVP wire events.

        `parent_trace_id` / `parent_agent_span_id` / `suppress_lifecycle`
        opt this translator into "delegated" mode — used by
        `traced_claude_sdk_client()` when an outer `AVPTracer` is already
        managing the run. In delegated mode the translator emits
        per-message events under the parent's trace_id/agent_span (so the
        wire is one tree) and skips its own `agent_started` / `at_end` /
        `agent_stopped` emission (the parent emits those on its own
        lifecycle bookends).
        """
        self.config = config
        self.on_event = on_event
        self._manifest = manifest
        self._prelude_emitted = False
        self._local_tools = local_tools
        self._local_tools_server_name = local_tools_server_name
        self._call_seq = itertools.count(1)
        self._sa_seq = itertools.count(1)
        self._step = 0
        self._started_at = now_iso()
        self._started_monotonic_ms = _monotonic_ms()
        # Span tree state. trace_id is allocated per run unless the
        # caller hands us a parent's IDs (delegated mode).
        self._trace_id = parent_trace_id or new_trace_id()
        self._agent_span_id = parent_agent_span_id or new_span_id()
        self._suppress_lifecycle = suppress_lifecycle
        # In delegated mode, push per-turn deltas into the parent tracer
        # so its cumulative state (agent_stopped totals) reflects this
        # translator's spend. Without this, the wire shows real per-turn
        # cost but agent_stopped reports zeros — see
        # `_handle_assistant_message` for the per-turn push.
        self._parent_tracer = parent_tracer
        self._current_turn_span_id: str | None = None
        self._tool_span_by_call_id: dict[str, str] = {}
        # Subagent lifecycle bookkeeping. The Claude Agent SDK surfaces a
        # subagent invocation as a parent-side `Agent` tool_use with
        # `input.subagent_type` naming the declared subagent. When PreToolUse
        # detects this we emit `subagent_invoked` (not `tool_invoked`) and
        # stash the frame span_id keyed by tool_use_id; PostToolUse pops it
        # and emits `subagent_returned`.
        self._subagents_by_name: dict[str, Subagent] = {
            sa.name: sa for sa in (config.subagents or [])
        }
        self._subagent_invocations: dict[
            str, dict[str, Any]
        ] = {}  # tool_use_id → {frame_span_id, sa_name, t0, invocation_id}
        self._total_turns = 0
        self._total_cost_usd = 0.0
        self._total_tokens = 0
        # Per-category running totals so the wire-side `avp.state` snapshot
        # can populate `tokens_input_total` etc. instead of leaving them
        # null. Updated alongside `_total_tokens` in _handle_assistant_message.
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cache_read = 0
        self._total_cache_write = 0
        self._tools_invoked: dict[str, int] = {}
        # Wall-clock t0 for the in-flight turn / each in-flight tool call,
        # used to compute `duration_ms` on model_turn_ended / tool_returned.
        self._turn_t0_monotonic_ms: int | None = None
        self._tool_t0_by_call_id: dict[str, int] = {}
        self._turn_open = False  # True between model_turn_started and model_turn_ended
        # Claude Agent SDK reports usage as cumulative-per-message, not per-turn delta.
        # We track the previous cumulative so we can compute this turn's actual cost.
        self._prev_cumulative_input_tokens = 0
        self._prev_cumulative_output_tokens = 0
        self._prev_cumulative_cache_read = 0
        self._prev_cumulative_cache_write = 0
        self._prev_cumulative_cost_usd = 0.0
        # Set by PreCompact / SubagentStart hooks so the next AssistantMessage's
        # cumulative-drop is treated as a deliberate baseline reset (graceful)
        # rather than as an unexpected accounting reset (errored).
        self._baseline_reset_pending = False
        # Stop hook may fire per-turn; informational only post-cut.
        self._stop_seen = False
        self._sdk_client_cls = sdk_client_cls
        self._sdk_options_cls = sdk_options_cls
        self._sdk_hook_matcher_cls = sdk_hook_matcher_cls
        self._sdk_agent_definition_cls = sdk_agent_definition_cls
        # `agent_started` is emitted post-`client.connect()` so its
        # `data.tools` / `data.skills` / `data.subagents` carry the
        # SDK's authoritative view (descriptions, agent type, skill
        # frontmatter). If connect() raises before we get there, the
        # exception path in run() falls back to bare cfg-only emission
        # so the lifecycle invariant (agent_started before agent_stopped)
        # holds.
        self._agent_started_emitted = False

    # ── Snapshot ────────────────────────────────────────────────────────────

    def _snapshot(self) -> RunStateSnapshot:
        return RunStateSnapshot(
            total_cost_usd=self._total_cost_usd,
            total_tokens=self._total_tokens,
            total_turns=self._total_turns,
            # Per-category running totals. Spec field; previously left null
            # because the agent only tracked the combined total. Emit None
            # when zero to avoid confusing consumers with "0 tokens used"
            # before any turn runs.
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

    def run(self) -> AgentStoppedEvent:
        """Start the Claude Agent SDK run and emit AVP events as it progresses.

        Returns the terminal AgentStoppedEvent."""
        # `agent_started` is emitted post-`client.connect()` so its
        # `tools` / `skills` / `subagents` carry SDK-side enrichment
        # (descriptions, agentType, source). The exception path below
        # falls back to cfg-only emission if connect raises.
        #
        # The run-prelude (run_requested + agent_described) fires FIRST,
        # before the SDK is touched. Even if connect raises, the wire
        # records who requested the run and who the agent is — that's
        # the audit fact, independent of whether the SDK ever spun up.
        self._emit_run_prelude()

        reason: StopReason
        error_msg: str | None = None
        try:
            asyncio.run(self._async_invoke_sdk())
            reason = StopReason.converged
        except KeyboardInterrupt:
            if not self._agent_started_emitted:
                self._emit_agent_started()
            reason = StopReason.interrupted
        except Exception as e:
            logger.exception("avp-claude-agent: SDK error")
            # Fallback: if SDK connect failed before we could fetch
            # enrichment, emit a bare cfg-only `agent_started` so the
            # wire still has the lifecycle marker before `agent_stopped`.
            if not self._agent_started_emitted:
                self._emit_agent_started()
            self._emit(
                ErrorOccurredEvent(
                    subject=self.config.run_id,
                    data=ErrorOccurredData(
                        **self._own_span(self._current_parent_for_run_event()),
                        **{
                            "avp.error.code": ErrorCode.agent_crash,
                            "avp.error.message": str(e),
                        },
                    ),
                )
            )
            reason = StopReason.error
            error_msg = str(e)
        finally:
            if self._turn_open:
                # Model was mid-turn when we exited — close the turn so the
                # trajectory is well-formed.
                assert self._current_turn_span_id is not None
                self._emit(
                    ModelTurnEndedEvent(
                        subject=self.config.run_id,
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

    # ── SDK integration ────────────────────────────────────────────────────

    async def _async_invoke_sdk(self) -> None:
        """Drive the Claude Agent SDK via ClaudeSDKClient.

        Drains the SDK's response stream until exhausted; the SDK owns the
        loop. v0.1 leaves bounded execution to the caller — the translator
        does not enforce caps.
        """
        if self._sdk_client_cls is None:
            from claude_agent_sdk import (
                AgentDefinition,
                ClaudeAgentOptions,
                ClaudeSDKClient,
                HookMatcher,
            )

            self._sdk_client_cls = ClaudeSDKClient
            self._sdk_options_cls = ClaudeAgentOptions
            self._sdk_hook_matcher_cls = HookMatcher
            self._sdk_agent_definition_cls = AgentDefinition

        options = self._build_sdk_options()
        prompt = self.config.prompt or ""

        async with self._sdk_client_cls(options=options) as client:
            await client.connect(prompt)
            # `agent_started` and the per-server `mcp_server_connected`
            # events both rely on SDK introspection that's only available
            # AFTER connect(): `get_context_usage()` returns the SDK's
            # tool / agent / skill catalog, and `get_mcp_status()`
            # returns the live MCP handshake outcome. Emitting at this
            # point makes the input event carry real descriptions,
            # agentType, skill frontmatter, and live MCP tool lists —
            # rather than name-only stubs the supervisor would have to
            # reconcile against post-hoc tool_invoked events.
            await self._emit_agent_started_with_sdk_enrichment(client)
            await self._emit_mcp_connections_after_connect(client)
            async for message in client.receive_response():
                self._on_sdk_message(message)

    def _build_sdk_options(self) -> Any:
        """Translate Commission → ClaudeAgentOptions.

        Mapping:
          - Commission.allowed_tools  → options.allowed_tools  (SDK enforces natively)
          - Commission.system_prompt  → options.system_prompt
          - Commission.model          → options.model
          - Commission.subagents      → options.agents = {name: AgentDefinition(...)}
          - Commission.mcp_servers    → options.mcp_servers — the SDK owns the
                                    connection lifecycle, tools/list discovery,
                                    and dispatch. Tools the SDK exposes from
                                    these servers surface to PreToolUse with
                                    the `mcp__<server>__<tool>` naming
                                    convention; we tag them on the AVP wire.
          - hooks={PreToolUse, PostToolUse} → translator-emitted tool_invoked / tool_returned
                                              OR subagent_invoked / subagent_returned when
                                              the tool_use is the SDK's `Agent` tool with
                                              a subagent_type matching a declared subagent
        """
        cfg = self.config
        assert self._sdk_options_cls is not None
        assert self._sdk_hook_matcher_cls is not None

        kwargs: dict[str, Any] = {}
        # AVP Commission.allowed_tools per SPEC.md §8.1: "the agent exposes ONLY
        # tools whose names are in this list" — that's exposure-filter
        # semantics. The Claude Agent SDK has TWO parameters with different
        # meanings (verified against `ClaudeAgentOptions` docstrings):
        #
        #   - `tools` — what the model CAN see. List restricts; `[]` disables
        #     all built-ins; `None` falls back to the `claude_code` preset.
        #   - `allowed_tools` — auto-execute without permission prompt. Does
        #     NOT restrict visibility.
        #
        # AVP semantics maps to SDK `tools`, not SDK `allowed_tools`. Earlier
        # versions mapped wrong — the model could see the full preset and
        # only auto-approval was filtered, breaking AVP's "MUST expose ONLY"
        # contract.
        if cfg.allowed_tools is not None:
            # Includes the empty-list case: AVP Commission.allowed_tools=[] means
            # "no tools at all," which maps to SDK tools=[].
            kwargs["tools"] = list(cfg.allowed_tools)
        if cfg.system_prompt:
            kwargs["system_prompt"] = cfg.system_prompt
        if cfg.model:
            kwargs["model"] = cfg.model
        if cfg.subagents:
            kwargs["agents"] = self._build_sdk_agents()
        if cfg.mcp_servers:
            kwargs["mcp_servers"] = self._build_sdk_mcp_servers()
        # Bridge any user-provided LocalTools into the SDK's in-process
        # MCP server slot so a single AVP-LocalTools registration works
        # across agents. Tools land on the wire as `mcp__<name>__<tool>`
        # and — because the bridged server is NOT in Commission.mcp_servers —
        # the existing tag-MCP-by-Commission logic correctly tags them as
        # `dispatch_target=local`.
        if self._local_tools is not None and self._local_tools.entries():
            from avp_claude_agent.local_tools_bridge import to_sdk_mcp_server

            kwargs.setdefault("mcp_servers", {})
            kwargs["mcp_servers"][self._local_tools_server_name] = to_sdk_mcp_server(
                self._local_tools, name=self._local_tools_server_name
            )

        kwargs["hooks"] = {
            "PreToolUse": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_pre_tool_use_hook]),
            ],
            "PostToolUse": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_post_tool_use_hook]),
            ],
            "UserPromptSubmit": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_user_prompt_submit_hook]),
            ],
            "Stop": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_stop_hook]),
            ],
            # PreCompact + SubagentStart signal the SDK is about to reset its
            # cumulative usage counters — the translator adopts the next
            # cumulative as a fresh baseline rather than emitting accounting_reset.
            "PreCompact": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_baseline_reset_hook]),
            ],
            "SubagentStart": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_baseline_reset_hook]),
            ],
        }

        # Forward the Claude CLI's stderr to the supervisor's stderr so users
        # can see the real reason if `Command failed with exit code 1` happens.
        # Without this the underlying CLI error is swallowed and only the
        # generic "Check stderr output for details" surfaces.
        import sys as _sys

        def _forward_stderr(line: str) -> None:
            _sys.stderr.write(f"[claude-cli] {line}")
            _sys.stderr.flush()

        kwargs.setdefault("stderr", _forward_stderr)

        return self._sdk_options_cls(**kwargs)

    def _build_sdk_agents(self) -> dict[str, Any]:
        """Translate Commission.subagents → ClaudeAgentOptions.agents.

        Maps the AVP Subagent shape onto Claude Agent SDK's `AgentDefinition`:

          AVP Subagent.name           → key in the agents dict
          AVP Subagent.description    → AgentDefinition.description
          AVP Subagent.system_prompt  → AgentDefinition.prompt
          AVP Subagent.model          → AgentDefinition.model
          AVP Subagent.allowed_tools  → AgentDefinition.tools (allowlist)

        v0.1 prototype: subagent.skills / inherit_tools / nested subagents
        are not yet wired into the SDK side. The Subagent type accepts them;
        this agent ignores them (with a warning would be louder, but the
        prototype's job is to demonstrate the wire shape, not ship full v1
        mapping).

        Falls back to constructing a plain dict when AgentDefinition isn't
        injected — the SDK accepts dicts in some versions; tests rely on this.
        """
        agents: dict[str, Any] = {}
        for sa in self.config.subagents or []:
            payload: dict[str, Any] = {"description": sa.description}
            if sa.system_prompt:
                payload["prompt"] = sa.system_prompt
            if sa.model:
                payload["model"] = sa.model
            if sa.allowed_tools is not None:
                payload["tools"] = list(sa.allowed_tools)
            if self._sdk_agent_definition_cls is not None:
                agents[sa.name] = self._sdk_agent_definition_cls(**payload)
            else:
                agents[sa.name] = payload
        return agents

    def _build_sdk_mcp_servers(self) -> dict[str, dict[str, Any]]:
        """Translate Commission.mcp_servers → ClaudeAgentOptions.mcp_servers.

        The Claude Agent SDK accepts a dict keyed by server id; each entry
        is a transport-shape dict ({type: stdio, command, args, env} or
        {type: http, url, headers}). The SDK owns connect / tools/list /
        dispatch from there.

        AVP's `avp://mcp/<id>` URI scheme uses the same `id` as the SDK's
        dict key — that's what links a `tool_exec_resolved` reply back to
        the originating server.
        """
        servers: dict[str, dict[str, Any]] = {}
        for s in self.config.mcp_servers or []:
            entry: dict[str, Any] = {"type": s.transport}
            if s.transport == "stdio":
                if s.command:
                    entry["command"] = list(s.command)
                if s.args:
                    entry["args"] = list(s.args)
                if s.env:
                    entry["env"] = dict(s.env)
            else:  # http
                if s.url:
                    entry["url"] = s.url
                if s.auth is not None:
                    # AVP's McpHttpAuth uses {type: bearer, token_env: ENV_VAR}.
                    # The SDK's HTTP transport expects an Authorization header;
                    # resolve the env var here so the secret never lands on
                    # the wire (Commission / events).
                    import os as _os

                    token = _os.environ.get(s.auth.token_env, "")
                    if token:
                        entry["headers"] = {"Authorization": f"Bearer {token}"}
            servers[s.id] = entry
        return servers

    @staticmethod
    def _mcp_server_id_from_tool_name(tool_name: str) -> str | None:
        """Claude Code's MCP tools follow the `mcp__<server_id>__<tool>`
        naming convention. Extract the server id, or None if this isn't
        an MCP-routed tool."""
        if not tool_name.startswith("mcp__"):
            return None
        rest = tool_name[len("mcp__") :]
        # Server ids may contain underscores; the separator between server
        # and tool name is exactly `__`. Split on the FIRST `__` after the
        # prefix; everything before is the server id, after is the tool.
        idx = rest.find("__")
        if idx <= 0:
            return None
        return rest[:idx]

    def _on_sdk_message(self, message: Any) -> None:
        """Route a single SDK Message instance to translator emitters.

        Type detection is duck-typed so tests can pass plain stand-ins."""
        cls = type(message).__name__
        if cls == "AssistantMessage":
            self._handle_assistant_message(message)
        elif cls == "ResultMessage":
            self._handle_result_message(message)
        # SystemMessage / UserMessage / others — the AVP wire doesn't surface them.

    def _handle_assistant_message(self, message: Any) -> None:
        """One AssistantMessage MAY correspond to one AVP turn — or not.

        SPEC.md §9.1: an AVP turn is one fresh model call. The Claude Agent
        SDK emits AssistantMessages for things that aren't fresh calls
        (continuations, internal restatements, follow-ups around tool
        results). We use the SDK's cumulative usage to detect: a message
        with NO new output tokens AND no fresh content is not a turn — skip
        the turn-started / turn-ended emission entirely.

        SPEC.md §9.4: when the SDK's cumulative drops without a deliberate
        reset signal (PreCompact / SubagentStart), emit error_occurred
        rather than silently clamping the delta.
        """
        cfg = self.config
        usage = getattr(message, "usage", None)
        model_id = getattr(message, "model", cfg.model or "unspecified")
        cumulative_ti, cumulative_to, cumulative_cr, cumulative_cw, cumulative_cost, cost_source = (
            _compute_cost(model_id, usage)
        )

        # Distinguish "this message carries no usage data" from "the SDK's
        # cumulative actually dropped." The Claude Agent SDK emits
        # AssistantMessages with `usage=None` or all-zero usage for
        # follow-up / continuation messages around tool results — those
        # aren't real turns and they're not accounting drops. A message
        # whose computed cumulative is all-zero AND that has no fresh
        # textual content is a non-turn carrier; skip both reset
        # detection AND turn emission. Without this guard, every
        # successful run that involves tool calls emits a spurious
        # `error_occurred(accounting_reset)` event when the post-tool
        # AssistantMessage arrives with no usage attached.
        no_usage = cumulative_ti == 0 and cumulative_to == 0 and cumulative_cost == 0.0
        has_text_content_now = any(
            type(b).__name__ == "TextBlock" and getattr(b, "text", "")
            for b in (getattr(message, "content", []) or [])
        )
        if no_usage and not has_text_content_now:
            return

        # Detect unexpected cumulative-reset BEFORE computing deltas.
        # `no_usage` runs here too — a sticky drop (cumulative dropped AND
        # the message DOES have content suggesting a real turn) still
        # triggers accounting_reset; that's the legitimate signal.
        unexpected_reset = (
            cumulative_ti < self._prev_cumulative_input_tokens
            or cumulative_to < self._prev_cumulative_output_tokens
            or cumulative_cost < self._prev_cumulative_cost_usd
        ) and not self._baseline_reset_pending
        if unexpected_reset:
            self._emit(
                ErrorOccurredEvent(
                    subject=cfg.run_id,
                    data=ErrorOccurredData(
                        **self._own_span(self._current_parent_for_run_event()),
                        **{
                            "avp.error.code": ErrorCode.accounting_reset,
                            "avp.error.message": (
                                "SDK cumulative usage dropped without a PreCompact / "
                                "SubagentStart signal. Per-turn deltas may be unreliable; "
                                "treat state.total_tokens / total_cost_usd as a lower bound."
                            ),
                        },
                    ),
                )
            )
            # Reset our baseline to the new cumulative so subsequent messages
            # produce sane deltas rather than a cascade of negative-delta errors.
            self._prev_cumulative_input_tokens = cumulative_ti
            self._prev_cumulative_output_tokens = cumulative_to
            self._prev_cumulative_cache_read = cumulative_cr
            self._prev_cumulative_cache_write = cumulative_cw
            self._prev_cumulative_cost_usd = cumulative_cost
            return

        if self._baseline_reset_pending:
            # PreCompact / SubagentStart fired: the next cumulative is a
            # fresh-start total, not a delta from prior. Adopt it directly.
            self._prev_cumulative_input_tokens = cumulative_ti
            self._prev_cumulative_output_tokens = cumulative_to
            self._prev_cumulative_cache_read = cumulative_cr
            self._prev_cumulative_cache_write = cumulative_cw
            self._prev_cumulative_cost_usd = cumulative_cost
            self._baseline_reset_pending = False
            # The first post-reset message IS a real turn IFF it has new content;
            # fall through to the regular emission path with prev=cum (delta=0).

        delta_ti = max(0, cumulative_ti - self._prev_cumulative_input_tokens)
        delta_to = max(0, cumulative_to - self._prev_cumulative_output_tokens)
        delta_cr = max(0, cumulative_cr - self._prev_cumulative_cache_read)
        delta_cw = max(0, cumulative_cw - self._prev_cumulative_cache_write)
        delta_cost = max(0.0, cumulative_cost - self._prev_cumulative_cost_usd)

        # Determine whether this message represents a real AVP turn. Two
        # signals: (a) the SDK reported new output tokens, OR (b) the message
        # carries content the model produced (TextBlocks). Empty deltas with
        # no content = SDK-internal restatement, not a turn.
        has_text_content = any(
            type(b).__name__ == "TextBlock" and getattr(b, "text", "")
            for b in (getattr(message, "content", []) or [])
        )
        is_real_turn = delta_to > 0 or has_text_content

        if not is_real_turn:
            # Don't bump _step or emit turn events — this isn't a turn.
            return

        self._step += 1
        self._current_turn_span_id = new_span_id()
        self._turn_t0_monotonic_ms = _monotonic_ms()
        self._emit(
            ModelTurnStartedEvent(
                subject=cfg.run_id,
                data=ModelTurnStartedData(
                    **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                    step=self._step,
                    # Claude Agent SDK is always streaming under the hood.
                    **{"gen_ai.request.stream": True},
                ),
            )
        )
        self._turn_open = True

        for block in getattr(message, "content", []) or []:
            btype = type(block).__name__
            if btype == "TextBlock":
                text = getattr(block, "text", None)
                if text:
                    self._emit(
                        TextEmittedEvent(
                            subject=cfg.run_id,
                            data=TextEmittedData(
                                **self._own_span(self._current_turn_span_id),
                                step=self._step,
                                **{"avp.text": text},
                            ),
                        )
                    )
            elif btype == "ThinkingBlock":
                # Extended-thinking block: chain-of-thought the model
                # exposed for this turn. Emit reasoning_emitted so audit
                # consumers can collapse / redact thinking from displays
                # without losing it from the trajectory. Anthropic also
                # returns a `signature` for replay across turns.
                rkwargs: dict[str, Any] = {
                    "avp.reasoning.text": getattr(block, "thinking", "") or "",
                }
                sig = getattr(block, "signature", None)
                if sig:
                    rkwargs["avp.reasoning.signature"] = sig
                self._emit(
                    ReasoningEmittedEvent(
                        subject=cfg.run_id,
                        data=ReasoningEmittedData(
                            **self._own_span(self._current_turn_span_id),
                            step=self._step,
                            **rkwargs,
                        ),
                    )
                )
            elif btype == "RedactedThinkingBlock":
                # Encrypted-only thinking: no plaintext, but record the
                # occurrence + signature so audit consumers can count
                # thinking turns even when the SDK doesn't expose content.
                rkwargs = {
                    "avp.reasoning.text": "",
                    "avp.reasoning.redacted": True,
                }
                sig = getattr(block, "data", None) or getattr(block, "signature", None)
                if sig:
                    rkwargs["avp.reasoning.signature"] = sig
                self._emit(
                    ReasoningEmittedEvent(
                        subject=cfg.run_id,
                        data=ReasoningEmittedData(
                            **self._own_span(self._current_turn_span_id),
                            step=self._step,
                            **rkwargs,
                        ),
                    )
                )
            # ToolUseBlock content is observed via the PreToolUse hook (which
            # fires in step with the SDK's actual tool dispatch).

        self._prev_cumulative_input_tokens = cumulative_ti
        self._prev_cumulative_output_tokens = cumulative_to
        self._prev_cumulative_cache_read = cumulative_cr
        self._prev_cumulative_cache_write = cumulative_cw
        self._prev_cumulative_cost_usd = cumulative_cost

        ended_kwargs: dict[str, Any] = {
            "gen_ai.usage.input_tokens": delta_ti,
            "gen_ai.usage.output_tokens": delta_to,
            # Always emit cache fields, even when 0, for consistency across
            # turns. Previously these were dropped on zero, so a turn-N event
            # wouldn't have the field at all while turn-N-1 did.
            "gen_ai.usage.cache_read.input_tokens": delta_cr,
            "gen_ai.usage.cache_creation.input_tokens": delta_cw,
            "avp.cost_usd": delta_cost,
            "avp.cost.source": cost_source,
            "gen_ai.response.model": model_id,
        }
        # gen_ai.response.finish_reasons — Anthropic returns `stop_reason`
        # ("end_turn", "tool_use", "max_tokens", "stop_sequence"). The OTel
        # convention is a list, so wrap.
        sdk_stop_reason = getattr(message, "stop_reason", None)
        if sdk_stop_reason:
            ended_kwargs["gen_ai.response.finish_reasons"] = [str(sdk_stop_reason)]

        # Wall-clock duration of the turn. Falls back to 0 if a message
        # arrived without a corresponding model_turn_started (shouldn't
        # happen, but the schema requires an int).
        turn_duration_ms = 0
        if self._turn_t0_monotonic_ms is not None:
            turn_duration_ms = max(0, _monotonic_ms() - self._turn_t0_monotonic_ms)
            self._turn_t0_monotonic_ms = None

        self._emit(
            ModelTurnEndedEvent(
                subject=cfg.run_id,
                data=ModelTurnEndedData(
                    **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                    step=self._step,
                    duration_ms=turn_duration_ms,
                    **ended_kwargs,
                ),
            )
        )
        self._turn_open = False

        self._total_turns += 1
        self._total_cost_usd += delta_cost
        self._total_tokens += delta_ti + delta_to
        # Per-category running totals so `avp.state.tokens_*_total` is
        # populated on every cost_recorded / agent_stopped snapshot.
        self._total_input_tokens += delta_ti
        self._total_output_tokens += delta_to
        self._total_cache_read += delta_cr
        self._total_cache_write += delta_cw
        # Delegated mode: also push the delta into the parent tracer's
        # cumulative state. Without this push, the parent's
        # `agent_stopped.avp_state` shows zeros even though the wire
        # carries real per-turn cost.
        if self._parent_tracer is not None:
            self._parent_tracer.accumulate_external(
                tokens_input=delta_ti,
                tokens_output=delta_to,
                cost_usd=delta_cost,
                cache_read=delta_cr,
                cache_write=delta_cw,
            )
        self._emit(
            CostRecordedEvent(
                subject=cfg.run_id,
                data=CostRecordedData(
                    **self._own_span(self._current_turn_span_id),
                    # Tag the source so consumers can join this event with
                    # the sibling `model_turn_ended.avp.cost.source`. The
                    # ResultMessage handler later emits a "reported"-tagged
                    # cost_recorded once the SDK returns the authoritative
                    # total.
                    **{
                        "avp.state": self._snapshot(),
                        "avp.cost.source": "computed",
                    },
                ),
            )
        )

    def _handle_result_message(self, message: Any) -> None:
        """ResultMessage closes the run with the SDK's authoritative cost
        total. We:

          1. Replace the running total with the SDK's number (their math
             beats ours — they have per-API-call truth we don't).
          2. Emit a final `cost_recorded` tagged `avp.cost.source=reported`
             so audit consumers can see the moment we switched from
             locally-computed estimates to provider-truth.

        Per-turn `model_turn_ended` events stay tagged as `computed`; the
        SDK doesn't expose per-turn cost on AssistantMessage. The
        reconciliation event surfaces the delta if anyone wants to
        cross-check our running estimate against the SDK total."""
        sdk_cost = getattr(message, "total_cost_usd", None)
        if sdk_cost is not None:
            self._total_cost_usd = float(sdk_cost)
            self._emit(
                CostRecordedEvent(
                    subject=self.config.run_id,
                    data=CostRecordedData(
                        **self._own_span(self._current_parent_for_run_event()),
                        **{
                            "avp.state": self._snapshot(),
                            "avp.cost.source": "reported",
                        },
                    ),
                )
            )

    # ── Hook callbacks (Claude Code hooks) ─────────────────────────────────

    async def _on_pre_tool_use_hook(
        self, input_data: dict[str, Any], tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK hook fired before each tool invocation. Emits tool_invoked —
        OR `subagent_invoked` if the tool_use is the SDK's `Agent` tool with
        a `subagent_type` matching a declared Commission.subagent.

        Returns `{}` (no override) — the translator observes; it does not gate."""
        call_id = str(input_data.get("tool_use_id") or tool_use_id or f"sdk-{next(self._call_seq)}")
        tool = str(input_data.get("tool_name", "unknown"))
        tool_input = input_data.get("tool_input", {}) or {}

        # Subagent dispatch: Claude Agent SDK exposes the parent's invocation
        # of a declared subagent as a `tool_use` whose name is `Agent` and
        # whose input includes `subagent_type`. The actual subagent run is
        # opaque to the parent's observer surface (per CASDK research) — the
        # parent only sees this one tool_use → tool_result pair. AVP surfaces
        # it as `subagent_invoked` / `subagent_returned` so consumers don't
        # have to special-case the `Agent` tool at every layer.
        sa_name: str | None = None
        if tool == "Agent":
            candidate = tool_input.get("subagent_type")
            if isinstance(candidate, str) and candidate in self._subagents_by_name:
                sa_name = candidate

        if sa_name is not None:
            self._handle_subagent_pre(call_id=call_id, sa_name=sa_name, tool_input=tool_input)
            return {}

        tool_span_id = new_span_id()
        self._tool_span_by_call_id[call_id] = tool_span_id
        # Stash wall-clock t0 so PostToolUse can compute duration_ms.
        self._tool_t0_by_call_id[call_id] = _monotonic_ms()
        parent = self._current_turn_span_id or self._agent_span_id

        # MCP-routed tools: SDK names them `mcp__<server>__<tool>`. Tag the
        # event so consumers can filter / correlate with mcp_server_connected.
        # Anything else dispatched by the SDK is a built-in (Read/Write/Bash/etc.)
        # — `local` from AVP's perspective.
        invoked_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": call_id,
            "gen_ai.tool.name": tool,
            "gen_ai.tool.call.arguments": dict(tool_input),
        }
        mcp_server_id = self._mcp_server_id_from_tool_name(tool)
        if mcp_server_id and self._is_declared_mcp_server(mcp_server_id):
            invoked_kwargs["avp.tool.dispatch_target"] = "mcp_server"
            invoked_kwargs["avp.mcp_server_id"] = mcp_server_id
        else:
            invoked_kwargs["avp.tool.dispatch_target"] = "local"

        self._emit(
            ToolInvokedEvent(
                subject=self.config.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, parent),
                    step=self._step,
                    **invoked_kwargs,
                ),
            )
        )
        self._tools_invoked[tool] = self._tools_invoked.get(tool, 0) + 1
        return {}

    def _is_declared_mcp_server(self, server_id: str) -> bool:
        """True iff `server_id` matches a `Commission.mcp_servers[].id`. Guards
        the dispatch_target tag — we only mark as MCP-routed when the
        server is explicitly declared, so a tool that happens to start
        with `mcp__` but came from elsewhere (filesystem-loaded MCP, SDK
        defaults) doesn't get mis-tagged."""
        return any(s.id == server_id for s in (self.config.mcp_servers or []))

    async def _on_post_tool_use_hook(
        self, input_data: dict[str, Any], tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK hook fired after each tool invocation. Emits tool_returned —
        OR `subagent_returned` if the matching pre-hook had diverted to the
        subagent lifecycle."""
        call_id = str(input_data.get("tool_use_id") or tool_use_id or "unknown")
        tool = str(input_data.get("tool_name", "unknown"))
        response = input_data.get("tool_response", "")

        if call_id in self._subagent_invocations:
            self._handle_subagent_post(call_id=call_id, response=response)
            return {}

        output: str
        output_structured: Any | None
        if not isinstance(response, str):
            try:
                import json

                output = json.dumps(response)
                output_structured = response
            except (TypeError, ValueError):
                output = str(response)
                output_structured = None
        else:
            output = response
            output_structured = None
        tool_span_id = self._tool_span_by_call_id.get(call_id, new_span_id())
        parent = self._current_turn_span_id or self._agent_span_id
        # duration_ms = wall clock between the matching PreToolUse and now.
        # Falls back to 0 if PreToolUse never recorded a t0 (race / hook
        # ordering edge case) — the schema requires an int ≥ 0.
        t0 = self._tool_t0_by_call_id.pop(call_id, None)
        tool_duration_ms = max(0, _monotonic_ms() - t0) if t0 is not None else 0
        returned_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": call_id,
            "gen_ai.tool.name": tool,
            "avp.tool.result.text": output,
        }
        if output_structured is not None:
            returned_kwargs["avp.tool.result.structured"] = output_structured
        self._emit(
            ToolReturnedEvent(
                subject=self.config.run_id,
                data=ToolReturnedData(
                    **self._shared_span(tool_span_id, parent),
                    step=self._step,
                    duration_ms=tool_duration_ms,
                    **returned_kwargs,
                ),
            )
        )
        return {}

    def _handle_subagent_pre(
        self, *, call_id: str, sa_name: str, tool_input: dict[str, Any]
    ) -> None:
        """Emit `subagent_invoked` and stash the frame state for the matching
        post-hook. Strips the SDK's `subagent_type` discriminator from the
        recorded input so the AVP wire shows just what the parent actually
        passed to the subagent (matches the AnthropicSubagentDriver shape)."""
        sa = self._subagents_by_name[sa_name]
        invocation_id = f"sa-{next(self._sa_seq)}"
        frame_span_id = new_span_id()
        self._tool_span_by_call_id[call_id] = frame_span_id
        self._tools_invoked[sa_name] = self._tools_invoked.get(sa_name, 0) + 1
        # Record bookkeeping so the post-hook can pair to this frame.
        self._subagent_invocations[call_id] = {
            "frame_span_id": frame_span_id,
            "sa_name": sa_name,
            "invocation_id": invocation_id,
            "t0_monotonic_ms": _monotonic_ms(),
        }
        # Sanitize the input — drop SDK-internal `subagent_type`. What's left
        # is what the parent agent actually intended to pass.
        sanitized_input = {k: v for k, v in tool_input.items() if k != "subagent_type"}
        parent = self._current_turn_span_id or self._agent_span_id
        invoked_data: dict[str, Any] = {
            "step": self._step,
            "gen_ai.agent.name": sa.name,
            "avp.subagent.invocation_id": invocation_id,
            "avp.subagent.input": sanitized_input,
        }
        if sa.description:
            invoked_data["gen_ai.agent.description"] = sa.description
        self._emit(
            SubagentInvokedEvent(
                subject=self.config.run_id,
                data=SubagentInvokedData(
                    **self._shared_span(frame_span_id, parent),
                    **invoked_data,
                ),
            )
        )

    def _handle_subagent_post(self, *, call_id: str, response: Any) -> None:
        """Emit `subagent_returned` paired with the matching `subagent_invoked`.

        The Claude Agent SDK does not surface the subagent's internal turns
        or per-subagent usage breakdown to the parent's observer surface —
        the wire shape from this agent is "thin": invoked + returned with
        no nested model_turn events and a zeroed-out `avp.subagent.usage`
        rollup. The subagent's actual spend is rolled into the parent's
        cumulative state via the SDK's own usage accounting (it counts as
        part of the parent run's tokens/cost), so the parent's
        RunStateSnapshot is correct; only the per-subagent attribution is
        unavailable here. Future versions may use the SDK's SubagentStart
        hook to recover some breakdown.
        """
        frame = self._subagent_invocations.pop(call_id)
        frame_span_id: str = frame["frame_span_id"]
        sa_name: str = frame["sa_name"]
        invocation_id: str = frame["invocation_id"]
        duration_ms = max(0, _monotonic_ms() - frame["t0_monotonic_ms"])

        # Coerce the SDK's tool_response (string or structured) into the AVP
        # text + structured pair, same convention tool_returned uses.
        if isinstance(response, str):
            result_text = response
            result_structured: Any | None = None
        else:
            try:
                import json

                result_text = json.dumps(response)
                result_structured = response
            except (TypeError, ValueError):
                result_text = str(response)
                result_structured = None

        # Per-subagent usage isn't surfaced by the SDK — emit a zero rollup.
        # The parent's cumulative RunStateSnapshot still includes the spend.
        zero_usage = RunStateSnapshot(total_cost_usd=0.0, total_tokens=0, total_turns=0)

        returned_data: dict[str, Any] = {
            "step": self._step,
            "gen_ai.agent.name": sa_name,
            "avp.subagent.invocation_id": invocation_id,
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
                subject=self.config.run_id,
                data=SubagentReturnedData(
                    **self._shared_span(frame_span_id, parent),
                    **returned_data,
                ),
            )
        )

    async def _on_user_prompt_submit_hook(
        self, _input_data: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK hook fired when a user prompt is submitted. v0.1: no-op
        observation point retained for symmetry with the SDK's hook surface."""
        return {}

    async def _on_stop_hook(
        self, _input_data: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK Stop hook. Records the signal; informational only post-cut."""
        self._stop_seen = True
        return {}

    async def _on_baseline_reset_hook(
        self, _input_data: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """PreCompact / SubagentStart fire BEFORE the SDK's cumulative usage
        counters reset. Mark the next AssistantMessage's cumulative as a
        fresh baseline rather than as a delta; this avoids spurious
        accounting_reset errors during legitimate context-management
        operations."""
        self._baseline_reset_pending = True
        return {}

    # ── AVP emission helpers ───────────────────────────────────────────────

    def _emit_run_prelude(self) -> None:
        """Emit `run_requested` (supervisor-attributed; agent-relayed) and
        `agent_described` (agent's manifest), the two events that open
        every AVP trajectory before `agent_started`.

        Skipped when running in delegated mode (parent tracer owns the
        lifecycle bookends) or when no manifest was supplied. Idempotent —
        run() may invoke this from both the normal-path and exception-path
        branches; the second call is a no-op.

        Both events are root-level (parent_span_id = ZERO) and sit above
        the `agent_started` span. Each owns a fresh span; they are not
        paired.
        """
        if self._suppress_lifecycle or self._manifest is None or self._prelude_emitted:
            return
        cfg = self.config
        sup = cfg.supervisor
        config_snapshot = cfg.model_dump(by_alias=True, exclude_none=True, mode="json")
        run_requested_kwargs: dict[str, Any] = {
            "avp.supervisor.name": sup.name if sup is not None else "unknown",
            "avp.commission": config_snapshot,
        }
        if sup is not None and sup.version is not None:
            run_requested_kwargs["avp.supervisor.version"] = sup.version
        self._emit(
            RunRequestedEvent(
                subject=cfg.run_id,
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
                subject=cfg.run_id,
                data=AgentDescribedData(
                    trace_id=self._trace_id,
                    span_id=new_span_id(),
                    parent_span_id=ZERO_SPAN_ID,
                    **{"avp.agent": self._manifest},
                ),
            )
        )
        self._prelude_emitted = True

    def _emit_agent_started(self, enrichment: dict[str, Any] | None = None) -> None:
        """Emit `agent_started` with the run's full tool / skill / subagent surface.

        `enrichment` is an optional mapping carrying SDK-side metadata
        the translator could only learn after the SDK connected (tool
        descriptions, agent type, skill descriptions from frontmatter).
        Shape:
            {
              "tools":     {tool_name: {"description": str | None}},
              "subagents": {subagent_name: {"description": str | None,
                                            "agent_type": str | None}},
              "skills":    {skill_name: {"description": str | None,
                                         "source": str | None}},
            }
        Missing entries fall back to whatever Commission provided. Callers
        on the synchronous fast path (tests, delegated mode) pass
        `enrichment=None` and get the v0.1 Commission-only emission.
        Callers on the live path build enrichment via
        `_fetch_sdk_enrichment(client)` after `client.connect()`.
        """
        # In delegated mode (running under an outer AVPTracer), the parent
        # already emitted agent_started — emitting again would put two
        # agent_started events on the wire under the same trace_id, which
        # consumers can't reconcile.
        if self._suppress_lifecycle:
            return
        if self._agent_started_emitted:
            # Idempotent: enriched post-connect emit takes precedence; a
            # later fallback in run()'s exception path becomes a no-op.
            return
        cfg = self.config
        enrichment = enrichment or {}
        tool_enrich: dict[str, dict[str, Any]] = enrichment.get("tools", {})
        subagent_enrich: dict[str, dict[str, Any]] = enrichment.get("subagents", {})
        skill_enrich: dict[str, dict[str, Any]] = enrichment.get("skills", {})
        # Build the effective tool surface the model sees, mirroring the
        # reference agent's "Commission.tools ∪ agent_builtin_tools, filtered
        # by allowed_tools" pattern (SPEC.md §13.1.2). For the CASDK agent,
        # the "agent builtins" are the Claude Agent SDK's own tools (Read,
        # Write, Bash, …) plus any MCP-routed names.
        #
        # Three Commission shapes drive different behaviors so the wire
        # accurately reflects what the model can actually see:
        #
        #   - `cfg.allowed_tools = ["Read", ...]` → restricted: surface
        #     exactly those names. SDK is told `tools=[...]` matching.
        #   - `cfg.allowed_tools = []` → no tools: emit empty surface
        #     (still distinguishes from "preset" — model sees nothing).
        #     SDK is told `tools=[]`.
        #   - `cfg.allowed_tools = None` (not set) → SDK uses the
        #     `claude_code` preset; surface the documented preset names
        #     so the audit trail isn't blank for the common
        #     "let-the-SDK-handle-it" case.
        tools_meta_list: list[dict[str, Any]] = []

        # Decide which built-in names to surface based on the Commission shape.
        # `cfg.allowed_tools is None` means "use SDK preset"; any list
        # (including empty) means "exactly these."
        if cfg.allowed_tools is None:
            builtin_names = list(_CLAUDE_CODE_PRESET_TOOLS)
        else:
            builtin_names = list(cfg.allowed_tools)

        for name in builtin_names:
            decl = _make_builtin_tool_decl(name)
            # Enrichment from get_context_usage() may carry a description
            # the SDK pulled from its own internal catalog or user-side
            # filesystem definitions. Only set when present; honest-null
            # otherwise.
            extra = tool_enrich.get(name) or {}
            if extra.get("description"):
                decl["description"] = extra["description"]
            tools_meta_list.append(decl)
        tools_meta = tools_meta_list or None
        # Same three-shape pattern as `tools` (above): None → SDK built-ins
        # surfaced; [] → empty surface (model has no subagents to delegate
        # to from a Commission-declared list, though SDK runtime may still
        # expose general-purpose); list → those names exactly. Built-in
        # subagents (currently just `general-purpose` per the Agent SDK
        # docs) get a name-only decl since the SDK doesn't expose their
        # description / system prompt / tools for us to authoritatively
        # report.
        subagents_meta_list: list[dict[str, Any]] = []
        rpc_subagent_names: set[str] = {sa.name for sa in (cfg.subagents or [])}
        if cfg.subagents:
            subagents_meta_list.extend(
                {
                    "name": sa.name,
                    "description": sa.description,
                    **({"inputSchema": sa.inputSchema} if sa.inputSchema is not None else {}),
                }
                for sa in cfg.subagents
            )
        if cfg.subagents is None:
            for name in _CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS:
                if name in rpc_subagent_names:
                    continue
                decl: dict[str, Any] = {"name": name}
                # Enrichment from get_context_usage().agents — when the
                # SDK reports the agent's description (typically from the
                # markdown source's frontmatter) and agentType.
                extra = subagent_enrich.get(name) or {}
                if extra.get("description"):
                    decl["description"] = extra["description"]
                if extra.get("agent_type"):
                    decl["avp.agent_type"] = extra["agent_type"]
                subagents_meta_list.append(decl)
        subagents_meta = subagents_meta_list or None
        # Skills: Commission-declared skills (cfg.skills) carry name + source.
        # Enrichment from get_context_usage().skills can add a description
        # parsed from SKILL.md frontmatter — that's the authoritative
        # description the SDK loaded.
        skills_meta_list: list[dict[str, Any]] = []
        for s in cfg.skills or []:
            decl: dict[str, Any] = {"name": s.name, "avp.source": s.avp_source}
            extra = skill_enrich.get(s.name) or {}
            if extra.get("description"):
                decl["description"] = extra["description"]
            skills_meta_list.append(decl)
        # If Commission didn't declare skills but the SDK loaded some from
        # user / project filesystem, surface those too.
        for name, extra in skill_enrich.items():
            if any(s["name"] == name for s in skills_meta_list):
                continue
            decl = {"name": name}
            if extra.get("description"):
                decl["description"] = extra["description"]
            if extra.get("source"):
                decl["avp.source"] = extra["source"]
            skills_meta_list.append(decl)
        skills_meta = skills_meta_list or None

        data_kwargs: dict[str, Any] = {
            "trace_id": self._trace_id,
            "span_id": self._agent_span_id,
            "parent_span_id": ZERO_SPAN_ID,
            "prompt": cfg.prompt,
            "system_prompt": cfg.system_prompt,
            "tools": tools_meta,
            "skills": skills_meta,
            "subagents": subagents_meta,
        }
        if cfg.model:
            data_kwargs["gen_ai.request.model"] = cfg.model
        # OTel-shaped operation + provider tags. Always set on agent_started:
        # the Claude Agent SDK is always an "invoke_agent" operation; the
        # provider is "anthropic" unless one of the SDK's backend env vars
        # selects Bedrock / Vertex / Foundry. See `_provider_from_env`.
        data_kwargs["gen_ai.operation.name"] = "invoke_agent"
        data_kwargs["gen_ai.provider.name"] = _provider_from_env()
        if cfg.thread_id:
            data_kwargs["avp.thread_id"] = cfg.thread_id
        if cfg.tags:
            data_kwargs["avp.tags"] = cfg.tags
        if cfg.meta:
            data_kwargs["avp.meta"] = cfg.meta
        self._emit(
            AgentStartedEvent(
                subject=cfg.run_id,
                data=AgentStartedData(**data_kwargs),
            )
        )
        self._agent_started_emitted = True
        # mcp_server_connected events are emitted later, AFTER the SDK
        # client connects and the MCP handshake completes. See
        # `_emit_mcp_connections_after_connect`. Pre-connect emission
        # (the v0.1 stub path) gave us the lifecycle marker but no
        # live tool data; post-connect gives both.

    async def _fetch_sdk_enrichment(self, client: Any) -> dict[str, Any]:
        """Pull the SDK's authoritative tool / agent / skill catalog via
        `ClaudeSDKClient.get_context_usage()` and reshape it into the
        enrichment dict `_emit_agent_started` consumes.

        Why post-connect: like `get_mcp_status`, this method only returns
        useful data after `client.connect()` has finished resolving the
        SDK's own tool catalog and reading filesystem-defined agents /
        skills.

        Defensive: if the method is missing (older SDK, test fakes),
        raises, or returns shapes we don't recognize, return an empty
        dict so the caller falls back to bare cfg-only emission.

        SDK shape (`ContextUsageResponse`):
            {
              "systemTools":     [{"name": str, "description": str?, ...}],
              "agents":          [{"agentType": str, "name": str?,
                                   "description": str?, "source": str?,
                                   ...}],
              "skills":          [{"name": str, "description": str?,
                                   "source": str?, ...}],
              "messageBreakdown": {...},  # not used here
              "mcpTools":         [...],   # surfaced via mcp_server_connected
            }
        Field names are camelCase per the TypedDict; we tolerate extras
        and missing fields without raising.
        """
        get_usage = getattr(client, "get_context_usage", None)
        if get_usage is None:
            return {}
        try:
            usage: Any = await get_usage()
        except Exception as e:
            logger.debug("get_context_usage failed; using cfg-only enrichment: %s", e)
            return {}
        if not isinstance(usage, dict):
            return {}

        enrichment: dict[str, dict[str, dict[str, Any]]] = {
            "tools": {},
            "subagents": {},
            "skills": {},
        }

        for entry in usage.get("systemTools") or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str):
                continue
            desc = entry.get("description")
            enrichment["tools"][name] = {
                "description": desc if isinstance(desc, str) else None,
            }

        for entry in usage.get("agents") or []:
            if not isinstance(entry, dict):
                continue
            # SDK exposes both `name` (display) and `agentType`
            # (programmatic key the SDK dispatches on). Index by
            # agentType so it matches what we surface as the subagent
            # name; fall back to `name` when agentType is missing.
            key = entry.get("agentType") or entry.get("name")
            if not isinstance(key, str):
                continue
            desc = entry.get("description")
            agent_type = entry.get("agentType")
            enrichment["subagents"][key] = {
                "description": desc if isinstance(desc, str) else None,
                "agent_type": agent_type if isinstance(agent_type, str) else None,
            }

        for entry in usage.get("skills") or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str):
                continue
            desc = entry.get("description")
            source = entry.get("source")
            enrichment["skills"][name] = {
                "description": desc if isinstance(desc, str) else None,
                "source": source if isinstance(source, str) else None,
            }

        return enrichment

    async def _emit_agent_started_with_sdk_enrichment(self, client: Any) -> None:
        """Fetch SDK enrichment, then emit `agent_started` with it.

        On any failure, falls back to cfg-only emission via
        `_emit_agent_started(enrichment=None)` so the lifecycle invariant
        (agent_started before agent_stopped) is preserved.
        """
        enrichment = await self._fetch_sdk_enrichment(client)
        self._emit_agent_started(enrichment=enrichment or None)

    async def _emit_mcp_connections_after_connect(self, client: Any) -> None:
        """Emit `mcp_server_connected` for each MCP server the SDK has
        actually connected to, using `ClaudeSDKClient.get_mcp_status()`.

        Why this is async + post-connect (not synchronous from
        `_emit_agent_started`): the Claude Agent SDK runs the MCP
        handshake (initialize + tools/list) AFTER `client.connect()`
        completes. Calling `get_mcp_status()` before then returns
        nothing useful. Emitting at this point gives us the SDK's
        authoritative view: actual server status (connected /
        failed / needs-auth / pending / disabled), real `serverInfo`
        (name + version), AND the live `tools` list per server.

        Fallback: if the SDK doesn't expose `get_mcp_status` (older
        version, test stubs without the method) or the call raises,
        fall back to the v0.1 stub behavior — emit a placeholder per
        Commission.mcp_servers entry with `tool_count=0` and no live
        tools, so the wire still records the lifecycle moment.
        """
        cfg = self.config
        get_status = getattr(client, "get_mcp_status", None)
        statuses: list[Any] = []
        if get_status is not None:
            try:
                response = await get_status()
                statuses = list(response.get("mcpServers", []) if response else [])
            except Exception as exc:
                logger.debug("get_mcp_status failed; falling back to stub events: %s", exc)
                statuses = []

        if statuses:
            for status in statuses:
                self._emit_mcp_connected_from_status(status)
            return

        # Fallback path: no live data, emit Commission-time stubs so the
        # lifecycle marker is at least present on the wire.
        if not cfg.mcp_servers:
            return
        for server in cfg.mcp_servers:
            self._emit(
                McpServerConnectedEvent(
                    subject=cfg.run_id,
                    data=McpServerConnectedData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "avp.mcp.server_id": server.id,
                            "avp.mcp.protocol_version": MCP_PROTOCOL_VERSION,
                            "avp.mcp.tool_count": 0,
                        },
                    ),
                )
            )

    def _emit_mcp_connected_from_status(self, status: Any) -> None:
        """Render one `McpServerStatus` (TypedDict / dict) into an
        `mcp_server_connected` event.

        `status` is the SDK's per-server snapshot — fields per the
        SDK's `McpServerStatus` TypedDict: `name`, `status`,
        `serverInfo` (NotRequired), `error` (NotRequired), `tools`
        (NotRequired list of `McpToolInfo`)."""
        cfg = self.config
        # status keys are camelCase per the SDK's TypedDict.
        server_id = str(status.get("name", ""))
        if not server_id:
            return
        server_info = status.get("serverInfo") or {}
        sdk_status = status.get("status")
        sdk_error = status.get("error")
        sdk_tools = status.get("tools") or []

        # Convert each McpToolInfo into a `_ToolDecl`-shaped dict for
        # the wire. `avp.dispatch_target=mcp_server` + `avp.mcp_server_id`
        # mirror what `tool_invoked` events for these tools will carry,
        # so consumers correlate connect → invoke uniformly.
        tools_decl: list[dict[str, Any]] = []
        for t in sdk_tools:
            tool_name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
            if not tool_name:
                continue
            decl: dict[str, Any] = {
                "name": tool_name,
                "avp.dispatch_target": "mcp_server",
                "avp.mcp_server_id": server_id,
            }
            tool_desc = (
                t.get("description") if isinstance(t, dict) else getattr(t, "description", None)
            )
            if tool_desc:
                decl["description"] = tool_desc
            tools_decl.append(decl)

        kwargs: dict[str, Any] = {
            "avp.mcp.server_id": server_id,
            "avp.mcp.protocol_version": MCP_PROTOCOL_VERSION,
            "avp.mcp.tool_count": len(tools_decl),
        }
        if server_info.get("name"):
            kwargs["avp.mcp.server_name"] = server_info["name"]
        if server_info.get("version"):
            kwargs["avp.mcp.server_version"] = server_info["version"]
        if tools_decl:
            kwargs["avp.mcp.tools"] = tools_decl
        if sdk_status:
            kwargs["avp.mcp.status"] = sdk_status
        if sdk_error:
            kwargs["avp.mcp.error"] = sdk_error

        self._emit(
            McpServerConnectedEvent(
                subject=cfg.run_id,
                data=McpServerConnectedData(
                    **self._own_span(self._agent_span_id),
                    **kwargs,
                ),
            )
        )

    def _emit_agent_stopped(
        self, reason: StopReason, *, error_msg: str | None = None
    ) -> AgentStoppedEvent | None:
        # In delegated mode the parent's __exit__ emits agent_stopped with
        # the parent's run state. Suppress here to avoid duplicates.
        if self._suppress_lifecycle:
            return None
        snap = self._snapshot()
        ev = AgentStoppedEvent(
            subject=self.config.run_id,
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


# Quiet unused-import warning for the `Source` re-export at top-level.
_ = Source
