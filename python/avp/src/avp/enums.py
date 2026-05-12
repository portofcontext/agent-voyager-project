"""Enums and small helpers for AVP v0.1 model."""

from __future__ import annotations

from enum import StrEnum


class Source(StrEnum):
    agent = "agent"
    supervisor = "supervisor"


class StopReason(StrEnum):
    """Why a run terminated. v0.1 keeps the enum tight: model said done,
    model declined, agent crashed, or operator interrupted. Cap-driven
    stop reasons (turn / token / cost / duration limits) are not part of
    v0.1; agents that need bounded execution wire it externally
    (subprocess timeouts, supervisor SIGKILL)."""

    converged = "converged"
    error = "error"
    interrupted = "interrupted"
    refused = "refused"


class ErrorCode(StrEnum):
    rate_limit = "rate_limit"
    context_limit = "context_limit"
    auth_error = "auth_error"
    agent_crash = "agent_crash"
    accounting_reset = "accounting_reset"
    unsupported_model = "unsupported_model"
    # Commission-managed-asset / resolver-protocol error codes (v0.1).
    resolver_not_configured = "resolver_not_configured"
    commission_collision = "commission_collision"
    # Runner determined its host execution environment can no longer
    # continue. Signal to the supervisor that the run is a rescue
    # candidate (see trajectory.md §7.3). Distinct from `agent_crash`,
    # which is an agent-internal failure.
    execution_backend_failure = "execution_backend_failure"
    unknown = "unknown"
