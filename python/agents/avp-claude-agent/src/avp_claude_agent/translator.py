"""ClaudeAgentTranslator — observer/translator that turns Claude Agent SDK
lifecycle events into AVP v0.1 events.

Structurally different from the driver-pattern adapter for the raw Anthropic
API (`avp-anthropic`): the Claude Agent SDK owns the agent loop, so we cannot
drive turns ourselves. Instead, we wire
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
    McpServerConnectedData,
    McpServerConnectedEvent,
    McpServerDisconnectedData,
    McpServerDisconnectedEvent,
    ModelTurnEndedData,
    ModelTurnEndedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    ReasoningEmittedData,
    ReasoningEmittedEvent,
    RefusalRecordedData,
    RefusalRecordedEvent,
    RunRequestedData,
    RunRequestedEvent,
    RunStateSnapshot,
    SkillLoadedData,
    SkillLoadedEvent,
    Source,
    StopReason,
    SubagentFailedData,
    SubagentFailedEvent,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentRef,
    SubagentReturnedData,
    SubagentReturnedEvent,
    TextEmittedData,
    TextEmittedEvent,
    ToolFailedData,
    ToolFailedEvent,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    new_span_id,
    new_trace_id,
)
from avp.agent.drivers import ResolveError, SubagentSpawnOutcome
from avp.enums import ErrorCode
from avp.types import (
    ManagedKind,
    ManagedRefResolvedData,
    ManagedRefResolvedEvent,
    ManagedRefResolveFailedData,
    ManagedRefResolveFailedEvent,
    now_iso,
)
from avp_claude_agent.builtin_tools import (
    CLAUDE_CODE_BUILTIN_TOOL_CATALOG,
    CLAUDE_CODE_PRESET_TOOLS,
)
from avp_claude_agent.builtin_tools import (
    SCHEMA_SNAPSHOT_DATE as BUILTIN_SCHEMA_SNAPSHOT_DATE,
)
from avp_claude_agent.builtin_tools import (
    SCHEMA_SOURCE as BUILTIN_SCHEMA_SOURCE,
)

# MCP protocol version we declare on `mcp_server_connected` events. Same
# value the AVP reference agent uses; tracks the upstream MCP spec.
MCP_PROTOCOL_VERSION = "2025-11-25"

# AssistantMessage.stop_reason values that indicate the model declined
# to produce useful output. Mapped to `avp.refusal_recorded` per
# trajectory.md §7. Anthropic ships "refusal" and "sensitive" as the
# two refusal-flavored codes today.
_REFUSAL_STOP_REASONS: frozenset[str] = frozenset({"refusal", "sensitive"})

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
# stays `commission.skills` only; we don't snapshot a "default skill list."
# Bundled skills mentioned in Claude Code docs (`/simplify`, `/debug`, etc.)
# are CLI features, not runtime-loaded artifacts the Python SDK exposes.


# The Claude Agent SDK delegates its preset tool catalog to the Claude
# Code CLI binary and does NOT expose it programmatically. To keep
# `agent_started.data.tools[]` self-describing, the preset name list and
# the per-tool input schemas live in `builtin_tools.py` as a maintained
# snapshot. Every emission carries `avp.tool.schema_source` and
# `avp.tool.schema_snapshot_date` so consumers can detect staleness.
_CLAUDE_CODE_PRESET_TOOLS = CLAUDE_CODE_PRESET_TOOLS


def _make_builtin_tool_decl(name: str) -> dict[str, Any]:
    """Build a `_ToolDecl`-shaped dict for one SDK-side tool name surfaced
    on `agent_started.data.tools`.

    For preset tools (Read, Write, Bash, Edit, Glob, Grep, WebFetch,
    WebSearch, Task, TodoWrite, NotebookEdit), look up the bundled
    `description` + `inputSchema` from `builtin_tools.CLAUDE_CODE_BUILTIN_TOOL_CATALOG`
    and tag the emission with `avp.tool.schema_source` +
    `avp.tool.schema_snapshot_date` so consumers know the provenance.

    For `mcp__<server>__<tool>` names the SDK uses for MCP-routed tools,
    tag `dispatch_target=mcp_server` + `avp.mcp_server_id` so consumers
    can correlate with `mcp_server_connected` events. The schema for
    those is surfaced separately on `mcp_server_connected.data.avp.mcp.tools[]`.

    For anything else (a name the SDK dispatches but isn't in our
    catalog — typically a new built-in we haven't snapshotted yet), fall
    back to name-only. PreToolUse / PostToolUse hooks still record the
    real input/output at dispatch time.
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
    decl: dict[str, Any] = {"name": name, "avp.dispatch_target": "local"}
    entry = CLAUDE_CODE_BUILTIN_TOOL_CATALOG.get(name)
    if entry is not None:
        decl["description"] = entry["description"]
        decl["inputSchema"] = entry["input_schema"]
        decl["avp.tool.schema_source"] = BUILTIN_SCHEMA_SOURCE
        decl["avp.tool.schema_snapshot_date"] = BUILTIN_SCHEMA_SNAPSHOT_DATE
    return decl


def _classify_sdk_exception(e: Exception) -> ErrorCode:
    """Map a Claude Agent SDK exception to an AVP ErrorCode.

    The SDK shells out to the `claude` CLI and surfaces provider failures
    through a small set of typed exceptions plus message text. We
    pattern-match by class name and message substrings — class-name match
    avoids importing claude_agent_sdk symbols at module top, which would
    make the translator unimportable in environments where the SDK isn't
    installed (mock-only tests, pre-flight `describe`).

    Falls back to `agent_crash` for unrecognized failures — the SDK
    surface is moving, so honest-unknown beats fabricated specificity.
    """
    type_name = type(e).__name__
    msg_lower = str(e).lower()

    # Provider-passthrough patterns. The SDK either re-raises Anthropic
    # SDK exceptions verbatim (when running against the API) or wraps
    # CLI stderr containing the same wording.
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
            "401",
            "403",
        )
    ):
        return ErrorCode.auth_error
    if any(
        phrase in msg_lower
        for phrase in (
            "prompt is too long",
            "context window",
            "maximum context length",
            "input is too long",
        )
    ):
        return ErrorCode.context_limit
    return ErrorCode.agent_crash


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
        commission: Commission,
        on_event: Callable[[BaseModel], None],
        *,
        resolver: Any | None = None,
        descriptor: AgentDescriptor | None = None,
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
        extra_sdk_options: dict[str, Any] | None = None,
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

        `extra_sdk_options` is a dict merged into the `ClaudeAgentOptions`
        passed to the SDK. Use it for SDK-specific concerns that don't
        belong on the AVP wire — e.g., `{"permission_mode":
        "bypassPermissions", "cwd": "/path/to/workspace",
        "add_dirs": ["/tmp/staging"]}`. These pass through opaque to
        AVP; consumers of the trajectory don't see them. Commission-level
        fields (`allowed_tools`, `system_prompt`, `model`, `subagents`,
        `mcp_servers`) take precedence — `extra_sdk_options` cannot
        override the AVP-spec wire shape.
        """
        self.commission = commission
        self.on_event = on_event
        self._resolver = resolver
        # Resolved material from the AVP Resolver API (see resolver.md).
        # Populated by `_resolve_managed_assets` before the SDK runs.
        self._resolved_mcp_servers: dict[str, dict[str, Any]] = {}
        self._resolved_skills: dict[str, dict[str, Any]] = {}
        self._resolved_subagents: dict[str, dict[str, Any]] = {}
        # Resolution bookkeeping populated by `_resolve_managed_assets_silently`
        # and replayed by `_emit_resolution_events` after `agent_started`,
        # so the wire order matches trajectory.md §2.2 (managed_ref_resolved
        # events come between agent_started and the first model_turn).
        self._resolved_records: list[dict[str, Any]] = []
        self._resolution_failure: dict[str, Any] | None = None
        # Idempotence flags for the lifecycle-fallback path on errors.
        self._resolution_events_emitted: bool = False
        self._skills_loaded_emitted: bool = False
        self._descriptor = descriptor
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
        self._extra_sdk_options = dict(extra_sdk_options or {})
        self._current_turn_span_id: str | None = None
        self._tool_span_by_call_id: dict[str, str] = {}
        # Subagent lifecycle bookkeeping. The Claude Agent SDK surfaces a
        # subagent invocation as a parent-side `Agent` tool_use with
        # `input.subagent_type` naming the declared subagent. When PreToolUse
        # detects this we emit `subagent_invoked` (not `tool_invoked`) and
        # stash the frame span_id keyed by tool_use_id; PostToolUse pops it
        # and emits `subagent_returned`.
        self._subagents_by_name: dict[str, SubagentRef] = {
            sa.id: sa for sa in (commission.subagents or [])
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
        # call_ids the PreToolUse hook gated with tool_failed (disabled
        # by allowlist or unknown to the effective tool bag). PostToolUse
        # SKIPS tool_returned for these so the wire shape (tool_invoked →
        # tool_failed, no tool_returned) is well-formed.
        self._tool_failed_call_ids: set[str] = set()
        # Set by `_handle_assistant_message` when stop_reason signals a
        # refusal; consumed by `run` / `run_scripted` to switch the final
        # `agent_stopped.reason` from converged to refused.
        self._refusal_seen: bool = False
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
        # exception path in run() falls back to bare commission-only emission
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

        Wire order, per trajectory.md §2.1 and §2.2:

          1. run_requested            (run prelude)
          2. agent_described          (run prelude)
          3. agent_started            (3rd in prelude, MUST fire even on
                                       validation / resolve failure)
          4. managed_ref_resolved*    (replay of silent-phase resolutions)
          5. mcp_server_connected*    (per declared server)
          6. skill_loaded*            (per skill with content)
          7. model_turn_* / tool_* / ... (drive)
          8. mcp_server_disconnected* (lifecycle bookend)
          9. agent_stopped

        Returns the terminal AgentStoppedEvent.
        """
        self._emit_run_prelude()
        # Spec §2.1: agent_started is the 3rd prelude event and MUST
        # fire on every trajectory, even when validation or resolution
        # fails. Built from declared sources (Commission + Descriptor +
        # bundled built-in catalog); the runtime SDK introspection step
        # we used to do here violated lifecycle ordering and is dropped.
        self._emit_agent_started()

        # Startup gates — fail-fast, agent_stopped(error) ends the run.
        if not self._validate_supported_model():
            return self._emit_agent_stopped(StopReason.error)
        if not self._validate_resolver_present():
            return self._emit_agent_stopped(StopReason.error)
        if not self._validate_no_collisions():
            return self._emit_agent_stopped(StopReason.error)
        if not self._validate_enabled_builtins():
            return self._emit_agent_stopped(StopReason.error)

        # Silent resolve. Records successes for replay; first failure
        # halts further resolves. Resolution events fire AFTER agent_started
        # (above) per §2.2, regardless of success or failure.
        if not self._resolve_managed_assets_silently():
            self._emit_resolution_events()
            self._resolution_events_emitted = True
            return self._emit_agent_stopped(StopReason.error)

        reason: StopReason
        error_msg: str | None = None
        try:
            asyncio.run(self._async_invoke_sdk())
            reason = StopReason.refused if self._refusal_seen else StopReason.converged
        except KeyboardInterrupt:
            self._emit_pending_lifecycle_events()
            reason = StopReason.interrupted
        except Exception as e:
            logger.exception("avp-claude-agent: SDK error")
            self._emit_pending_lifecycle_events()
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
                # Model was mid-turn when we exited — close the turn so the
                # trajectory is well-formed.
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
            # mcp_server_disconnected events sit between the last model
            # turn and agent_stopped per trajectory.md §4.
            self._emit_mcp_disconnected_stubs()

        return self._emit_agent_stopped(reason, error_msg=error_msg)

    def _emit_pending_lifecycle_events(self) -> None:
        """If the SDK loop raised before its normal emission point, emit
        the resolution / skills_loaded events here so the wire still
        carries them before agent_stopped. Idempotent via instance flags."""
        if not self._resolution_events_emitted:
            self._emit_resolution_events()
            self._resolution_events_emitted = True
        if not self._skills_loaded_emitted:
            self._emit_skills_loaded()
            self._skills_loaded_emitted = True

    # ── SDK integration ────────────────────────────────────────────────────

    async def _async_invoke_sdk(self) -> None:
        """Drive the Claude Agent SDK via ClaudeSDKClient.

        Wire order inside this method (continuing the prelude `run()`
        emitted):

          agent_started (with SDK enrichment, post-connect)
            → managed_ref_resolved* (replay from silent phase)
            → mcp_server_connected* (per server)
            → skill_loaded* (per skill with content)
            → drive `client.receive_response()` → _on_sdk_message

        The conformance harness substitutes a fake `ClaudeSDKClient` via
        `_sdk_client_cls`; the rest of the orchestration is identical.
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
        prompt = self.commission.prompt or ""

        async with self._sdk_client_cls(options=options) as client:
            await client.connect(prompt)
            # agent_started already fired in run() (spec §2.1 requires
            # it 3rd in the prelude, before any validation / resolve).
            # Here we emit the events that fall between agent_started and
            # the first model_turn_started per §2.2:
            #   managed_ref_resolved → mcp_server_connected → skill_loaded.
            self._emit_resolution_events()
            self._resolution_events_emitted = True
            await self._emit_mcp_connections_after_connect(client)
            self._emit_skills_loaded()
            self._skills_loaded_emitted = True
            # Drive turns.
            async for message in client.receive_response():
                self._on_sdk_message(message)

    # ── Resolver protocol (spec/v0.1/resolver.md) ────────────────────────────────────────

    def _has_managed_assets(self) -> bool:
        c = self.commission
        return bool(c.mcp_servers or c.skills or c.subagents)

    def _emit_error(self, code: ErrorCode, message: str) -> None:
        """Emit a single `error_occurred` event at the agent span. Used by
        startup gates that fail-fast before the main loop opens."""
        self._emit(
            ErrorOccurredEvent(
                subject=self.commission.run_id,
                data=ErrorOccurredData(
                    **self._own_span(self._agent_span_id),
                    **{"avp.error.code": code, "avp.error.message": message},
                ),
            )
        )

    def _validate_resolver_present(self) -> bool:
        """If the Commission carries managed assets but no ResolverDriver
        was supplied (and AVP_RESOLVER_URL was not bootstrapped into one),
        fail-fast with `resolver_not_configured` (spec/v0.1/resolver.md §2)."""
        if not self._has_managed_assets():
            return True
        if self._resolver is not None:
            return True
        self._emit_error(
            ErrorCode.resolver_not_configured,
            (
                "Commission carries managed assets but no ResolverDriver "
                "was supplied to ClaudeAgentTranslator (and AVP_RESOLVER_URL "
                "was not bootstrapped). Configure a resolver service per `spec/v0.1/resolver.md` §2."
            ),
        )
        return False

    def _validate_supported_model(self) -> bool:
        """Cross-check `Commission.model` against the descriptor's
        `supported_models` (glob list). Skipped when no Descriptor is
        published, the Descriptor declares no constraint, or the Commission
        omits `model`. Mirrors AVPAgent's gate."""
        import fnmatch

        descriptor = self._descriptor
        commission = self.commission
        if descriptor is None or descriptor.supported_models is None:
            return True
        if not commission.model:
            return True
        if any(fnmatch.fnmatchcase(commission.model, p) for p in descriptor.supported_models):
            return True
        self._emit_error(
            ErrorCode.unsupported_model,
            (
                f"Commission.model={commission.model!r} is not supported by "
                f"{descriptor.agent_name}@{descriptor.agent_version}; "
                f"supported_models={descriptor.supported_models}"
            ),
        )
        return False

    def _validate_no_collisions(self) -> bool:
        """Detect id/name collisions between agent-internal contributions
        and Commission-declared entries. Mirrors AVPAgent's gate. Covers:

          - `Commission.subagents[].id` ↔ built-in tool names
          - `Commission.subagents[].id` ↔ descriptor.built_in_subagents[].name
          - `Commission.mcp_servers[].id` ↔ same two surfaces
        """
        commission = self.commission
        descriptor = self._descriptor
        # Built-in tool surface: the bundled preset (Claude Code tools) plus
        # any descriptor-published tool catalog.
        builtin_tool_names: set[str] = set(CLAUDE_CODE_PRESET_TOOLS)
        if descriptor is not None:
            builtin_tool_names |= {t.name for t in (descriptor.built_in_tools or [])}
            builtin_subagent_names = {s.name for s in (descriptor.built_in_subagents or [])}
        else:
            builtin_subagent_names = set()

        commission_subagent_ids = {sa.id for sa in (commission.subagents or [])}
        commission_mcp_ids = {m.id for m in (commission.mcp_servers or [])}

        collisions: list[str] = []
        for entry_id in commission_subagent_ids & builtin_tool_names:
            collisions.append(f"subagent id {entry_id!r} collides with a built-in tool name")
        for entry_id in commission_subagent_ids & builtin_subagent_names:
            collisions.append(
                f"subagent id {entry_id!r} collides with a descriptor-declared built-in subagent"
            )
        for entry_id in commission_mcp_ids & builtin_tool_names:
            collisions.append(f"mcp_server id {entry_id!r} collides with a built-in tool name")
        for entry_id in commission_mcp_ids & builtin_subagent_names:
            collisions.append(
                f"mcp_server id {entry_id!r} collides with a descriptor-declared built-in subagent"
            )
        if not collisions:
            return True
        self._emit_error(ErrorCode.commission_collision, "; ".join(collisions))
        return False

    def _validate_enabled_builtins(self) -> bool:
        """Validate `Commission.enabled_builtin_*` allowlists against the
        agent's descriptor-published built-in surfaces. Unknown names are
        configuration mistakes that fail-fast. Mirrors AVPAgent's gate."""
        commission = self.commission
        descriptor = self._descriptor

        # Tool catalog: descriptor wins when present; bundled preset is the
        # fallback so a translator without a descriptor still has a name set
        # to validate against.
        if descriptor is not None and descriptor.built_in_tools is not None:
            known_tools = {t.name for t in descriptor.built_in_tools}
        else:
            known_tools = set(CLAUDE_CODE_PRESET_TOOLS)
        if descriptor is not None and descriptor.built_in_subagents is not None:
            known_subagents = {s.name for s in descriptor.built_in_subagents}
        else:
            known_subagents = set()
        if descriptor is not None and descriptor.built_in_skills is not None:
            known_skills = {s.name for s in descriptor.built_in_skills}
        else:
            known_skills = set()

        unknown: list[str] = []
        for name in commission.enabled_builtin_tools or []:
            if name not in known_tools:
                unknown.append(f"enabled_builtin_tools: {name!r} not in agent's built-in tools")
        for name in commission.enabled_builtin_subagents or []:
            if name not in known_subagents:
                unknown.append(
                    f"enabled_builtin_subagents: {name!r} not in agent's built-in subagents"
                )
        for name in commission.enabled_builtin_skills or []:
            if name not in known_skills:
                unknown.append(f"enabled_builtin_skills: {name!r} not in agent's built-in skills")

        if not unknown:
            return True
        self._emit_error(ErrorCode.commission_collision, "; ".join(unknown))
        return False

    def _resolve_managed_assets_silently(self) -> bool:
        """Walk Commission-managed assets, call the resolver for each,
        populate `self._resolved_*` maps WITHOUT emitting events. Returns
        False on the first failure (short-circuits — kind/id matched per
        spec/v0.1/resolver.md §5).

        Why silent: spec/v0.1/trajectory.md §2.1 requires
        `run_requested → agent_described → agent_started` in that exact
        order, and §2.2 requires `managed_ref_resolved` events to fall
        between `agent_started` and the first `model_turn_started`.
        Resolution itself must happen BEFORE `agent_started` so the
        merged-view event can list resolved descriptions. We square this
        by separating "do the work" from "emit the events" — the silent
        phase fills internal state; `_emit_resolution_events` replays the
        round-trips after `agent_started` fires.
        """
        commission = self.commission
        if not self._has_managed_assets():
            return True
        assert self._resolver is not None

        kind_passes: tuple[tuple[ManagedKind, Any, dict[str, dict[str, Any]]], ...] = (
            ("mcp_server", commission.mcp_servers or [], self._resolved_mcp_servers),
            ("skill", commission.skills or [], self._resolved_skills),
            ("subagent", commission.subagents or [], self._resolved_subagents),
        )
        for kind, entries, target_map in kind_passes:
            for entry in entries:
                ok, material = self._resolve_one_silent(kind, entry.id, entry.ref)
                if not ok:
                    return False
                target_map[entry.id] = material
        return True

    def _resolve_one_silent(
        self, kind: ManagedKind, entry_id: str, ref: Any
    ) -> tuple[bool, dict[str, Any]]:
        """Call the resolver for one entry; record success / failure in
        instance state. No event emission. Successes append to
        `_resolved_records`; the first failure goes into
        `_resolution_failure` (subsequent failures are not recorded
        because we short-circuit)."""
        assert self._resolver is not None
        t0 = _monotonic_ms()
        try:
            material = self._resolver.resolve(kind=kind, id=entry_id, ref=ref)
        except ResolveError as e:
            self._resolution_failure = {
                "kind": kind,
                "id": entry_id,
                "error": str(e),
                "error_code": e.code,
            }
            return False, {}
        except Exception as e:
            self._resolution_failure = {
                "kind": kind,
                "id": entry_id,
                "error": f"{type(e).__name__}: {e}",
                "error_code": "driver_exception",
            }
            return False, {}
        duration_ms = max(0, _monotonic_ms() - t0)
        self._resolved_records.append({"kind": kind, "id": entry_id, "duration_ms": duration_ms})
        return True, dict(material) if material else {}

    def _emit_resolution_events(self) -> None:
        """Replay `managed_ref_resolved` for each successful resolution
        recorded during the silent phase, then `managed_ref_resolve_failed`
        for the first failure (if any). Ordered as the original resolver
        calls were made."""
        commission = self.commission
        for rec in self._resolved_records:
            self._emit(
                ManagedRefResolvedEvent(
                    subject=commission.run_id,
                    data=ManagedRefResolvedData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "avp.managed.kind": rec["kind"],
                            "avp.managed.id": rec["id"],
                            "duration_ms": rec["duration_ms"],
                        },
                    ),
                )
            )
        if self._resolution_failure is not None:
            f = self._resolution_failure
            kwargs: dict[str, Any] = {
                "avp.managed.kind": f["kind"],
                "avp.managed.id": f["id"],
                "avp.resolve.error": f["error"],
            }
            if f["error_code"] is not None:
                kwargs["avp.resolve.error.code"] = f["error_code"]
            self._emit(
                ManagedRefResolveFailedEvent(
                    subject=commission.run_id,
                    data=ManagedRefResolveFailedData(
                        **self._own_span(self._agent_span_id),
                        **kwargs,
                    ),
                )
            )

    def _emit_skills_loaded(self) -> None:
        """One `skill_loaded` event per resolved skill whose body actually
        entered the system prompt (i.e. the resolver returned `content`).
        Honest-silent for metadata-only resolutions — the registration
        view is `agent_started.data.skills`."""
        for entry in self.commission.skills or []:
            material = self._resolved_skills.get(entry.id) or {}
            if not material.get("content"):
                continue
            self._emit(
                SkillLoadedEvent(
                    subject=self.commission.run_id,
                    data=SkillLoadedData(
                        **self._own_span(self._agent_span_id),
                        step=0,
                        **{"avp.skill.name": entry.id},
                    ),
                )
            )

    def _build_sdk_options(self) -> Any:
        """Translate Commission → ClaudeAgentOptions.

        Mapping (refs-only Commission):
          - Commission.system_prompt              → options.system_prompt
          - Commission.model                      → options.model
          - Commission.enabled_builtin_tools      → options.tools (allowlist
                                                    against the SDK's preset)
          - Commission.{mcp_servers,subagents}    → not set here. Managed
                                                    assets are dereferenced
                                                    via the AVP resolver
                                                    protocol and applied to
                                                    the SDK options elsewhere
                                                    in the translator.
          - hooks={PreToolUse, PostToolUse}       → translator-emitted
                                                    tool_invoked / tool_returned
                                                    plus subagent lifecycle
                                                    when the SDK dispatches its
                                                    own built-in subagents.
        """
        commission = self.commission
        assert self._sdk_options_cls is not None
        assert self._sdk_hook_matcher_cls is not None

        kwargs: dict[str, Any] = {}
        # Commission.enabled_builtin_tools is the v0.1 allowlist. Absent →
        # SDK uses its full preset (no `tools` kwarg). Present → pass the
        # named subset to the SDK's `tools` parameter; the SDK enforces.
        # Names that aren't in the SDK preset are AVPAgent's startup-validation
        # responsibility (commission_collision); reaching here means they
        # already passed Descriptor cross-check.
        # NOTE on filesystem discovery: the Claude Agent SDK auto-loads
        # skills from `~/.claude/skills/` and subagents from
        # `.claude/agents/` unless `setting_sources` is overridden. AVP
        # discloses this on the Descriptor (`filesystem-discovery-available`
        # capability) and leaves the SDK's default in place — passing
        # `setting_sources=[]` here cascades into the SDK's tool-definition
        # loading and `permission_mode` resolution in ways that aren't
        # ours to redesign. Supervisors who want strict no-discovery set
        # the SDK options themselves via `extra_sdk_options` (typically
        # alongside a compatible `permission_mode`).
        allow = commission.enabled_builtin_tools
        if allow is not None:
            kwargs["tools"] = list(allow)
        # Compose system prompt from Commission.system_prompt plus any
        # resolved skill SKILL.md bodies. v0.1 convention: skills inject
        # eagerly at startup as a system-prompt suffix.
        system_parts: list[str] = []
        if commission.system_prompt:
            system_parts.append(commission.system_prompt)
        for entry in commission.skills or []:
            content = (self._resolved_skills.get(entry.id) or {}).get("content")
            if content:
                system_parts.append(f'<skill name="{entry.id}">\n{content}\n</skill>')
        if system_parts:
            kwargs["system_prompt"] = "\n\n".join(system_parts)
        if commission.model:
            kwargs["model"] = commission.model
        # Resolved managed assets land on the SDK's `mcp_servers` /
        # `agents` kwargs.
        sdk_mcp_servers = self._build_sdk_mcp_servers()
        if sdk_mcp_servers:
            kwargs["mcp_servers"] = sdk_mcp_servers
        sdk_agents = self._build_sdk_agents()
        if sdk_agents:
            kwargs["agents"] = sdk_agents
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

        # Merge in user-supplied SDK-specific options (permission_mode,
        # cwd, add_dirs, can_use_tool, etc.). Commission-derived kwargs
        # already in `kwargs` take precedence; extra_sdk_options can't
        # override AVP wire-shape concerns like `tools` (which maps from
        # Commission.enabled_builtin_tools).
        for k, v in self._extra_sdk_options.items():
            kwargs.setdefault(k, v)

        return self._sdk_options_cls(**kwargs)

    def _build_sdk_agents(self) -> dict[str, Any]:
        """Translate resolved managed subagents → SDK `AgentDefinition` dict.

        The AVP resolver returns model-facing metadata for each
        `Commission.subagents[]` entry: `name`, optional `description`,
        optional `inputSchema`. The Claude Agent SDK's `agents` parameter
        accepts a `{name: AgentDefinition(description, prompt, model, tools)}`
        dict; we map AVP's metadata onto it. Fields the AVP resolver
        doesn't surface (system_prompt, model, tools) stay unset, so the
        SDK uses its own defaults. A future spec revision can extend the
        resolver result shape if a real implementation needs them.
        """
        out: dict[str, Any] = {}
        for entry in self.commission.subagents or []:
            material = self._resolved_subagents.get(entry.id) or {}
            payload: dict[str, Any] = {}
            description = material.get("description")
            if description:
                payload["description"] = description
            # CASDK's `AgentDefinition` requires `prompt`. Resolvers SHOULD
            # supply one in `system_prompt` / `prompt`; if they don't, fall
            # back to the description or a synthesized "you are <name>" so
            # construction doesn't crash. Real supervisors should publish a
            # proper prompt; this default is a floor, not a recommendation.
            payload["prompt"] = (
                material.get("system_prompt")
                or material.get("prompt")
                or description
                or f"You are the {entry.id} subagent."
            )
            model = material.get("model")
            if model:
                payload["model"] = model
            tools = material.get("tools")
            if isinstance(tools, list):
                payload["tools"] = list(tools)
            if self._sdk_agent_definition_cls is not None and payload:
                out[entry.id] = self._sdk_agent_definition_cls(**payload)
            else:
                out[entry.id] = payload or {"description": ""}
        return out

    def _build_sdk_mcp_servers(self) -> dict[str, dict[str, Any]]:
        """Translate resolved managed MCP servers → SDK `mcp_servers` dict.

        The Claude Agent SDK accepts a `{server_id: {type, ...}}` dict
        keyed by server id; each entry carries transport-shape fields
        (`{type: stdio, command, args, env}` or `{type: http, url, headers}`).
        The resolver returns whatever connection material the supervisor
        configured; we map the common shapes through.
        """
        out: dict[str, dict[str, Any]] = {}
        for entry in self.commission.mcp_servers or []:
            material = self._resolved_mcp_servers.get(entry.id) or {}
            transport = material.get("transport")
            sdk_entry: dict[str, Any] = {}
            if transport == "stdio":
                sdk_entry["type"] = "stdio"
                if isinstance(material.get("command"), list):
                    sdk_entry["command"] = list(material["command"])
                if isinstance(material.get("args"), list):
                    sdk_entry["args"] = list(material["args"])
                if isinstance(material.get("env"), dict):
                    sdk_entry["env"] = dict(material["env"])
            elif transport == "http":
                sdk_entry["type"] = "http"
                url = material.get("url")
                if url:
                    sdk_entry["url"] = url
                auth = material.get("auth")
                if isinstance(auth, dict):
                    token = auth.get("token")
                    if token:
                        sdk_entry["headers"] = {"Authorization": f"Bearer {token}"}
                headers = material.get("headers")
                if isinstance(headers, dict):
                    sdk_entry.setdefault("headers", {}).update(headers)
            else:
                # Unknown / unset transport — pass through the raw shape so a
                # supervisor experimenting with a transport AVP doesn't
                # know about can still wire the SDK up (the SDK validates).
                sdk_entry.update(material)
            out[entry.id] = sdk_entry
        return out

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

        trajectory.md §3.1: an AVP turn is one fresh model call. The
        Claude Agent SDK emits AssistantMessages for things that aren't
        fresh calls (continuations, internal restatements, follow-ups
        around tool results). We use the SDK's cumulative usage to
        detect: a message with NO new output tokens AND no fresh content
        is not a turn — skip the turn-started / turn-ended emission
        entirely.

        trajectory.md §3.3: when the SDK's cumulative drops without a
        deliberate reset signal (PreCompact / SubagentStart), emit
        error_occurred rather than silently clamping the delta.
        """
        commission = self.commission
        usage = getattr(message, "usage", None)
        model_id = getattr(message, "model", commission.model or "unspecified")
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
                    subject=commission.run_id,
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
                subject=commission.run_id,
                data=ModelTurnStartedData(
                    **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                    step=self._step,
                    # Claude Agent SDK is always streaming under the hood.
                    **{"gen_ai.request.stream": True},
                ),
            )
        )
        self._turn_open = True

        # Walk content blocks and collect text / reasoning payloads
        # WITHOUT emitting yet. Per trajectory.md §7 (and the reasoning
        # case), reasoning_emitted and text_emitted come AFTER
        # model_turn_ended ("model_turn_ended → reasoning_emitted →
        # text_emitted" — thought, then spoke). ToolUseBlock content is
        # observed separately via the PreToolUse hook.
        text_payloads: list[str] = []
        reasoning_payloads: list[dict[str, Any]] = []
        for block in getattr(message, "content", []) or []:
            btype = type(block).__name__
            if btype == "TextBlock":
                text = getattr(block, "text", None)
                if text:
                    text_payloads.append(text)
            elif btype == "ThinkingBlock":
                # Extended-thinking block: chain-of-thought the model
                # exposed for this turn. We surface as reasoning_emitted
                # so audit consumers can collapse / redact thinking from
                # displays without losing it from the trajectory.
                # Anthropic also returns a `signature` for replay.
                rkwargs: dict[str, Any] = {
                    "avp.reasoning.text": getattr(block, "thinking", "") or "",
                }
                sig = getattr(block, "signature", None)
                if sig:
                    rkwargs["avp.reasoning.signature"] = sig
                reasoning_payloads.append(rkwargs)
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
                reasoning_payloads.append(rkwargs)

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
                subject=commission.run_id,
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
                subject=commission.run_id,
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

        # Deferred emission: reasoning, then text. Order matches
        # trajectory.md §7 — "thought, then spoke" reconstructs the
        # turn for audit consumers, and gives them a place to collapse
        # / redact chain-of-thought without losing it from the wire.
        for rkwargs in reasoning_payloads:
            self._emit(
                ReasoningEmittedEvent(
                    subject=commission.run_id,
                    data=ReasoningEmittedData(
                        **self._own_span(self._current_turn_span_id),
                        step=self._step,
                        **rkwargs,
                    ),
                )
            )
        for text in text_payloads:
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

        # Refusal detection. Anthropic signals refusal via
        # `stop_reason="refusal"` or `"sensitive"`; the model's refusal
        # text (when given) is in the TextBlock(s) we already emitted.
        # We surface a structured `refusal_recorded` event and flip a
        # one-way bit that the run() / run_scripted() callers consult to
        # set agent_stopped.reason=refused.
        if sdk_stop_reason and sdk_stop_reason in _REFUSAL_STOP_REASONS:
            refusal_kwargs: dict[str, Any] = {
                "step": self._step,
                "avp.refusal.reason": str(sdk_stop_reason),
                "avp.refusal.provider": "anthropic",
            }
            refusal_text = " ".join(p for p in text_payloads if p).strip()
            if refusal_text:
                refusal_kwargs["avp.refusal.message"] = refusal_text
            self._emit(
                RefusalRecordedEvent(
                    subject=commission.run_id,
                    data=RefusalRecordedData(
                        **self._own_span(self._current_turn_span_id),
                        **refusal_kwargs,
                    ),
                )
            )
            self._refusal_seen = True

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
                    subject=self.commission.run_id,
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
                subject=self.commission.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, parent),
                    step=self._step,
                    **invoked_kwargs,
                ),
            )
        )
        self._tools_invoked[tool] = self._tools_invoked.get(tool, 0) + 1

        # Runtime gate: even when an allowlist filters the tool surface
        # on `agent_started`, a misbehaving model can still call a hidden
        # name (prompt injection, hallucination). The wire records the
        # attempt (tool_invoked above) and the refusal (tool_failed
        # below); the actual tool MUST NOT execute. Same shape AVPAgent
        # uses (trajectory.md §4, commission.md §4).
        block_reason = self._classify_tool_dispatch_failure(tool)
        if block_reason is not None:
            self._emit(
                ToolFailedEvent(
                    subject=self.commission.run_id,
                    data=ToolFailedData(
                        **self._shared_span(tool_span_id, parent),
                        step=self._step,
                        **{
                            "gen_ai.tool.call.id": call_id,
                            "gen_ai.tool.name": tool,
                            "avp.tool.error": block_reason[0],
                            "avp.tool.error.code": block_reason[1],
                        },
                    ),
                )
            )
            # Suppress the matching tool_returned: when the SDK's
            # PostToolUse fires later, we won't double-emit.
            self._tool_failed_call_ids.add(call_id)
        return {}

    def _classify_tool_dispatch_failure(self, tool: str) -> tuple[str, str] | None:
        """Return (error_message, error_code) when a tool MUST fail at
        dispatch — disabled by allowlist, or unknown to the effective
        tool bag. Returns None for tools that should execute normally.

        Effective tool bag: built-in tools (descriptor.built_in_tools
        when set, else the bundled preset), MCP-routed names prefixed
        `mcp__<server>__`, the `Agent` subagent dispatcher.
        """
        commission = self.commission
        # MCP-routed name → recognized iff the server id is declared in
        # Commission.mcp_servers OR matches the local-tools bridge's
        # synthetic server name (which mounts user-supplied local tools
        # under `mcp__<local_tools_server_name>__*`).
        if tool.startswith("mcp__"):
            mcp_server_id = self._mcp_server_id_from_tool_name(tool)
            if mcp_server_id and (
                self._is_declared_mcp_server(mcp_server_id)
                or mcp_server_id == self._local_tools_server_name
            ):
                return None
            return (f"Unknown tool {tool!r}", "unknown_tool")
        # `Agent` is always known when there are subagents; routed
        # through _handle_subagent_pre earlier in the hook.
        if tool == "Agent":
            return None
        # Built-in: name set from descriptor when present, else bundled preset.
        descriptor = self._descriptor
        if descriptor is not None and descriptor.built_in_tools is not None:
            builtin_names = {t.name for t in descriptor.built_in_tools}
        else:
            builtin_names = set(CLAUDE_CODE_PRESET_TOOLS)
        if tool not in builtin_names:
            return (f"Unknown tool {tool!r}", "unknown_tool")
        # Built-in name: check Commission.enabled_builtin_tools allowlist.
        allow = commission.enabled_builtin_tools
        if allow is not None and tool not in allow:
            return (
                f"Tool {tool!r} is disabled by Commission.enabled_builtin_tools",
                "disabled_builtin",
            )
        return None

    def _is_declared_mcp_server(self, server_id: str) -> bool:
        """True iff `server_id` matches a `Commission.mcp_servers[].id`. Guards
        the dispatch_target tag — we only mark as MCP-routed when the
        server is explicitly declared, so a tool that happens to start
        with `mcp__` but came from elsewhere (filesystem-loaded MCP, SDK
        defaults) doesn't get mis-tagged."""
        return any(s.id == server_id for s in (self.commission.mcp_servers or []))

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
        # The pre-hook already emitted tool_failed for this call_id —
        # skip tool_returned so the wire records only invoked→failed
        # (no execution).
        if call_id in self._tool_failed_call_ids:
            self._tool_failed_call_ids.discard(call_id)
            self._tool_span_by_call_id.pop(call_id, None)
            self._tool_t0_by_call_id.pop(call_id, None)
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
                subject=self.commission.run_id,
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
        """Emit `subagent_invoked`, delegate to the resolver, and stash the
        outcome for the matching post-hook.

        When `self._resolver` is configured (the supervisor stood up the
        AVP resolver service), the parent agent MUST route declared-subagent
        dispatch through `avp.spawn_subagent` (resolver.md §4). The resolver
        returns a `SubagentSpawnOutcome` carrying the child run id, result
        text, reason, and usage rollup — those are what `subagent_invoked`
        and `subagent_returned`/`subagent_failed` carry on the wire.

        Without a resolver (no managed-subagent contract), we fall back to
        the thin observer shape: emit `subagent_invoked` with no child
        run_id, let the SDK execute the subagent in-process, and surface
        the SDK's tool_response on `subagent_returned`.
        """
        sa = self._subagents_by_name[sa_name]
        invocation_id = f"sa-{next(self._sa_seq)}"
        frame_span_id = new_span_id()
        self._tool_span_by_call_id[call_id] = frame_span_id
        self._tools_invoked[sa_name] = self._tools_invoked.get(sa_name, 0) + 1

        # Sanitize the input — drop SDK-internal `subagent_type`. What's left
        # is what the parent agent actually intended to pass.
        sanitized_input = {k: v for k, v in tool_input.items() if k != "subagent_type"}

        # Delegate to the resolver if configured. spawn_subagent failures
        # (raises) get recorded as a transport-level error and trigger
        # subagent_failed at frame close, mirroring AVPAgent.
        spawn_outcome: SubagentSpawnOutcome | None = None
        spawn_error: tuple[str, str | None] | None = None
        if self._resolver is not None:
            try:
                spawn_outcome = self._resolver.spawn_subagent(
                    run_id=self.commission.run_id,
                    id=sa.id,
                    ref=sa.ref,
                    input=sanitized_input,
                )
            except Exception as e:
                spawn_error = (f"{type(e).__name__}: {e}", "spawn_transport_error")

        self._subagent_invocations[call_id] = {
            "frame_span_id": frame_span_id,
            "sa_name": sa_name,
            "invocation_id": invocation_id,
            "t0_monotonic_ms": _monotonic_ms(),
            "spawn_outcome": spawn_outcome,
            "spawn_error": spawn_error,
        }

        # Resolved metadata enriches the invoked-event payload.
        resolved = self._resolved_subagents.get(sa.id) or {}
        description = resolved.get("description")

        invoked_data: dict[str, Any] = {
            "step": self._step,
            "gen_ai.agent.name": sa.id,
            "gen_ai.operation.name": "invoke_agent",
            "avp.subagent.invocation_id": invocation_id,
            "avp.subagent.input": sanitized_input,
        }
        if description:
            invoked_data["gen_ai.agent.description"] = description
        if spawn_outcome is not None and spawn_outcome.child_run_id:
            invoked_data["avp.subagent.run_id"] = spawn_outcome.child_run_id

        parent = self._current_turn_span_id or self._agent_span_id
        self._emit(
            SubagentInvokedEvent(
                subject=self.commission.run_id,
                data=SubagentInvokedData(
                    **self._shared_span(frame_span_id, parent),
                    **invoked_data,
                ),
            )
        )

    def _handle_subagent_post(self, *, call_id: str, response: Any) -> None:
        """Close the subagent frame. Emit `subagent_returned` from the
        resolver's spawn outcome — OR `subagent_failed` when the resolver
        call raised or the outcome carries an error.

        Without a resolver, fall back to the thin observer shape using
        the SDK's tool_response: zero usage, reason=converged, no
        child_run_id. That path matters only for production deployments
        without a supervisor resolver (rare for managed subagents, since
        Commission.subagents implies the supervisor is wiring one up)."""
        frame = self._subagent_invocations.pop(call_id)
        frame_span_id: str = frame["frame_span_id"]
        sa_name: str = frame["sa_name"]
        invocation_id: str = frame["invocation_id"]
        duration_ms = max(0, _monotonic_ms() - frame["t0_monotonic_ms"])
        spawn_outcome: SubagentSpawnOutcome | None = frame.get("spawn_outcome")
        spawn_error: tuple[str, str | None] | None = frame.get("spawn_error")

        parent = self._current_turn_span_id or self._agent_span_id

        # Error path: resolver raised, OR resolver returned an outcome with
        # `error` set (child run crashed, model rejected, etc.).
        error_msg: str | None = None
        error_code: str | None = None
        if spawn_error is not None:
            error_msg, error_code = spawn_error
        elif spawn_outcome is not None and spawn_outcome.error is not None:
            error_msg = spawn_outcome.error
            error_code = spawn_outcome.error_code
        if error_msg is not None:
            failed_kwargs: dict[str, Any] = {
                "step": self._step,
                "gen_ai.agent.name": sa_name,
                "avp.subagent.invocation_id": invocation_id,
                "duration_ms": duration_ms,
                "avp.subagent.error": error_msg,
            }
            if error_code:
                failed_kwargs["avp.subagent.error.code"] = error_code
            self._emit(
                SubagentFailedEvent(
                    subject=self.commission.run_id,
                    data=SubagentFailedData(
                        **self._shared_span(frame_span_id, parent),
                        **failed_kwargs,
                    ),
                )
            )
            return

        # Success path. Prefer the resolver's spawn outcome (full
        # child_run_id / usage); fall back to the SDK's tool_response
        # only when no resolver was configured.
        if spawn_outcome is not None:
            result_text = spawn_outcome.text
            result_structured = spawn_outcome.structured
            reason = spawn_outcome.reason
            usage = spawn_outcome.usage
        else:
            if isinstance(response, str):
                result_text = response
                result_structured = None
            else:
                try:
                    import json

                    result_text = json.dumps(response)
                    result_structured = response
                except (TypeError, ValueError):
                    result_text = str(response)
                    result_structured = None
            reason = StopReason.converged
            usage = RunStateSnapshot(total_cost_usd=0.0, total_tokens=0, total_turns=0)

        returned_data: dict[str, Any] = {
            "step": self._step,
            "gen_ai.agent.name": sa_name,
            "avp.subagent.invocation_id": invocation_id,
            "duration_ms": duration_ms,
            "avp.subagent.result.text": result_text,
            "avp.subagent.reason": reason,
            "avp.subagent.usage": usage,
        }
        if result_structured is not None:
            returned_data["avp.subagent.result.structured"] = result_structured

        self._emit(
            SubagentReturnedEvent(
                subject=self.commission.run_id,
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
        `agent_described` (agent's Descriptor), the two events that open
        every AVP trajectory before `agent_started`.

        Skipped when running in delegated mode (parent tracer owns the
        lifecycle bookends) or when no Descriptor was supplied. Idempotent —
        run() may invoke this from both the normal-path and exception-path
        branches; the second call is a no-op.

        Both events are root-level (parent_span_id = ZERO) and sit above
        the `agent_started` span. Each owns a fresh span; they are not
        paired.
        """
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
        commission = self.commission
        enrichment = enrichment or {}
        tool_enrich: dict[str, dict[str, Any]] = enrichment.get("tools", {})
        subagent_enrich: dict[str, dict[str, Any]] = enrichment.get("subagents", {})
        skill_enrich: dict[str, dict[str, Any]] = enrichment.get("skills", {})
        # Effective tool surface for `agent_started.data.tools[]`.
        # Source preference:
        #   1. descriptor.built_in_tools, when set (it's authoritative per
        #      agent-descriptor.md; lets supervisors / tests inject a
        #      different catalog than the SDK's bundled preset);
        #   2. CLAUDE_CODE_PRESET_TOOLS otherwise (the Claude Agent SDK
        #      ships these even when the agent doesn't ship a Descriptor).
        # Filter the result by `Commission.enabled_builtin_tools` if set.
        # MCP-server tools surface separately on
        # `mcp_server_connected.data.avp.mcp.tools[]` after handshake.
        descriptor_tools: list[dict[str, Any]] | None = None
        if self._descriptor is not None and self._descriptor.built_in_tools is not None:
            descriptor_tools = [
                t.model_dump(mode="json", by_alias=True, exclude_none=True)
                for t in self._descriptor.built_in_tools
            ]

        allow = commission.enabled_builtin_tools
        allow_set: set[str] | None = set(allow) if allow is not None else None

        tools_meta_list: list[dict[str, Any]] = []
        if descriptor_tools is not None:
            for entry in descriptor_tools:
                name = entry.get("name")
                if not isinstance(name, str):
                    continue
                if allow_set is not None and name not in allow_set:
                    continue
                decl: dict[str, Any] = {"name": name, "avp.dispatch_target": "local"}
                if entry.get("description"):
                    decl["description"] = entry["description"]
                if entry.get("inputSchema"):
                    decl["inputSchema"] = entry["inputSchema"]
                tools_meta_list.append(decl)
        else:
            if allow_set is None:
                preset_subset = list(_CLAUDE_CODE_PRESET_TOOLS)
            else:
                preset_subset = [n for n in _CLAUDE_CODE_PRESET_TOOLS if n in allow_set]
            for name in preset_subset:
                decl = _make_builtin_tool_decl(name)
                extra = tool_enrich.get(name) or {}
                if extra.get("description"):
                    decl["description"] = extra["description"]
                tools_meta_list.append(decl)
        tools_meta = tools_meta_list or None

        # Subagent surface. Commission-managed subagents are refs-only and
        # need the resolver to materialize metadata; v0.1 surfaces them as
        # id-only stubs (consumers correlate with managed_ref_resolved
        # events). SDK built-in subagents (general-purpose) are surfaced
        # when present in enrichment.
        subagents_meta_list: list[dict[str, Any]] = []
        if commission.subagents:
            subagents_meta_list.extend({"name": sa.id} for sa in commission.subagents)
        for name in _CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS:
            if any(d["name"] == name for d in subagents_meta_list):
                continue
            decl: dict[str, Any] = {"name": name}
            extra = subagent_enrich.get(name) or {}
            if extra.get("description"):
                decl["description"] = extra["description"]
            if extra.get("agent_type"):
                decl["avp.agent_type"] = extra["agent_type"]
            subagents_meta_list.append(decl)
        subagents_meta = subagents_meta_list or None

        # Skills surface. Commission-managed skills are enriched from the
        # resolver's payload (SKILL.md frontmatter carries `description`
        # and the resolver returns it alongside `content`). Resolution has
        # already run by the time `_emit_agent_started` is called, so
        # `self._resolved_skills` is populated. Filesystem-discovered
        # skills (when the SDK is configured to read them) surface via
        # `skill_enrich`.
        skills_meta_list: list[dict[str, Any]] = []
        if commission.skills:
            for s in commission.skills:
                decl: dict[str, Any] = {"name": s.id}
                material = self._resolved_skills.get(s.id) or {}
                if description := material.get("description"):
                    decl["description"] = description
                if source := material.get("source") or material.get("avp.source"):
                    decl["avp.source"] = source
                skills_meta_list.append(decl)
        for name, extra in skill_enrich.items():
            if any(d["name"] == name for d in skills_meta_list):
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
            "prompt": commission.prompt,
            "system_prompt": commission.system_prompt,
            "tools": tools_meta,
            "skills": skills_meta,
            "subagents": subagents_meta,
        }
        if commission.model:
            data_kwargs["gen_ai.request.model"] = commission.model
        # OTel-shaped operation + provider tags. Always set on agent_started:
        # the Claude Agent SDK is always an "invoke_agent" operation; the
        # provider is "anthropic" unless one of the SDK's backend env vars
        # selects Bedrock / Vertex / Foundry. See `_provider_from_env`.
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
        dict so the caller falls back to bare commission-only emission.

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
            logger.debug("get_context_usage failed; using commission-only enrichment: %s", e)
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

        On any failure, falls back to commission-only emission via
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
        self._emit_mcp_connected_stubs()

    def _emit_mcp_connected_stubs(self) -> None:
        """Emit one `mcp_server_connected` per declared Commission entry
        with `tool_count=0` and no live tool catalog. Used in two places:

          - production fallback when `get_mcp_status` isn't available or
            returns nothing (older SDK, handshake didn't surface state);
          - `run_scripted` (no live SDK) so the conformance lifecycle
            marker is on the wire.
        """
        commission = self.commission
        if not commission.mcp_servers:
            return
        for server in commission.mcp_servers:
            self._emit(
                McpServerConnectedEvent(
                    subject=commission.run_id,
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

    def _emit_mcp_disconnected_stubs(self) -> None:
        """Emit one `mcp_server_disconnected` per declared Commission MCP
        server entry. Paired with `_emit_mcp_connected_stubs`. Fires
        before `agent_stopped` so the supervisor sees the lifecycle bookend.
        """
        commission = self.commission
        if not commission.mcp_servers:
            return
        for server in commission.mcp_servers:
            self._emit(
                McpServerDisconnectedEvent(
                    subject=commission.run_id,
                    data=McpServerDisconnectedData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "avp.mcp.server_id": server.id,
                            "avp.mcp.disconnect_reason": "clean",
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
        commission = self.commission
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
                subject=commission.run_id,
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


# Quiet unused-import warning for the `Source` re-export at top-level.
_ = Source
