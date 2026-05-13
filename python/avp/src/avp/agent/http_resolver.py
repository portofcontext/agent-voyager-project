"""HTTP-backed `ResolverDriver` for the AVP resolver protocol (spec/resolver/v0.1-beta/resolver.md).

The agent's bootstrap reads `AVP_RESOLVER_URL` from the environment (the
supervisor sets it when spawning the agent). At startup, the agent calls
`avp.resolve` once per `Commission.{mcp_servers,skills,subagents}[]`
entry; on subagent invocation it calls `avp.spawn_subagent`. AVP itself
does not specify auth or transport — both are deployment-layer concerns.
This implementation handles the common case: JSON-RPC 2.0 over HTTP,
with optional `Authorization: Bearer <token>` from an env var the
supervisor chooses.

Zero new dependencies: built on `urllib.request` (stdlib). Production
deployments wanting async / connection pooling / custom retries can
implement their own `ResolverDriver` directly.
"""

from __future__ import annotations

import itertools
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import JsonValue

from avp.agent.drivers import ResolveError, ResolverDriver, SubagentSpawnOutcome
from avp.enums import StopReason
from avp.types import ManagedKind, RunStateSnapshot

_DEFAULT_TIMEOUT_S = 30.0
_USER_AGENT = "avp-resolver-client/0.1"


class HttpResolver(ResolverDriver):
    """JSON-RPC 2.0 resolver client over HTTP.

    Construct directly when wiring in production code:

        resolver = HttpResolver(url="https://resolver.acme.internal/avp",
                                bearer_token=os.environ["MY_TOKEN"])

    Or use :func:`http_resolver_from_env` for the common case where the
    supervisor configures the agent's environment via `AVP_RESOLVER_URL`
    and `AVP_RESOLVER_TOKEN`.
    """

    def __init__(
        self,
        url: str,
        *,
        bearer_token: str | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if not url:
            raise ValueError("HttpResolver requires a non-empty URL")
        self._url = url
        self._bearer = bearer_token
        self._timeout = timeout_s
        self._extra_headers = dict(extra_headers or {})
        self._call_seq = itertools.count(1)

    def _next_id(self) -> str:
        return f"avp-rpc-{next(self._call_seq)}"

    def _post(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if self._bearer:
            headers["Authorization"] = f"Bearer {self._bearer}"
        for k, v in self._extra_headers.items():
            headers[k] = v
        req = Request(self._url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                response_body = resp.read()
        except HTTPError as e:
            # JSON-RPC errors typically arrive as 200 with `error` body;
            # an HTTP-level error means transport / auth / wrong endpoint.
            raise ResolveError(
                f"resolver HTTP {e.code}: {e.reason}",
                code=f"http_{e.code}",
            ) from e
        except URLError as e:
            raise ResolveError(
                f"resolver unreachable: {e.reason}",
                code="transport_error",
            ) from e

        try:
            envelope = json.loads(response_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ResolveError(
                f"resolver returned non-JSON response: {e}",
                code="malformed_response",
            ) from e

        if not isinstance(envelope, dict):
            raise ResolveError(
                f"resolver response is not a JSON-RPC envelope: {type(envelope).__name__}",
                code="malformed_response",
            )

        error = envelope.get("error")
        if error is not None:
            if isinstance(error, dict):
                msg = error.get("message") or "resolver returned error"
                code = error.get("code")
                code_str = str(code) if code is not None else None
                raise ResolveError(msg, code=code_str)
            raise ResolveError(f"resolver returned non-conforming error: {error!r}")

        result = envelope.get("result")
        if not isinstance(result, dict):
            raise ResolveError(
                f"resolver result is not an object: {type(result).__name__}",
                code="malformed_response",
            )
        return result

    def resolve(self, *, kind: ManagedKind, id: str, ref: JsonValue) -> dict[str, Any]:
        # `run_id` isn't strictly part of the AVPAgent's resolver-call API
        # surface — the agent doesn't pass it through to this method. It's
        # available in HttpResolver's run-context if a future refactor
        # wants it; for now per spec/resolver/v0.1-beta/resolver.md §3 we include kind/id/ref.
        return self._post(
            "avp.resolve",
            {"kind": kind, "id": id, "ref": ref},
        )

    def spawn_subagent(
        self,
        *,
        run_id: str,
        id: str,
        ref: JsonValue,
        input: dict[str, Any],
    ) -> SubagentSpawnOutcome:
        result = self._post(
            "avp.spawn_subagent",
            {"run_id": run_id, "id": id, "ref": ref, "input": dict(input)},
        )

        # Per spec/resolver/v0.1-beta/resolver.md §4 the result shape carries `subagent_run_id` and an
        # inline summary block. Be permissive about missing fields so a
        # resolver that returns less than the spec wants still produces a
        # usable outcome — the parent records what it got and stops on
        # `error` if set.
        summary = result.get("result") or {}
        if not isinstance(summary, dict):
            summary = {}
        child_run_id = str(
            result.get("subagent_run_id") or summary.get("subagent_run_id") or f"sub-{run_id}-{id}"
        )
        usage_spec = summary.get("usage") or {}
        usage = RunStateSnapshot(
            total_cost_usd=float(usage_spec.get("total_cost_usd", 0.0)),
            total_tokens=int(usage_spec.get("total_tokens", 0)),
            total_turns=int(usage_spec.get("total_turns", 0)),
            tokens_input_total=usage_spec.get("tokens_input_total"),
            tokens_output_total=usage_spec.get("tokens_output_total"),
        )
        reason_raw = summary.get("reason", StopReason.converged)
        reason = StopReason(reason_raw) if isinstance(reason_raw, str) else reason_raw
        return SubagentSpawnOutcome(
            child_run_id=child_run_id,
            text=str(summary.get("text", "")),
            structured=summary.get("structured"),
            reason=reason,
            duration_ms=int(summary.get("duration_ms", 0)),
            usage=usage,
            error=summary.get("error"),
            error_code=summary.get("error_code"),
        )


def http_resolver_from_env(
    *,
    url_env_var: str = "AVP_RESOLVER_URL",
    token_env_var: str = "AVP_RESOLVER_TOKEN",
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> HttpResolver | None:
    """Construct an `HttpResolver` from the supervisor-configured environment.

    Returns `None` when `AVP_RESOLVER_URL` is unset or empty, signaling
    the no-managed-assets case. The agent's startup gate then rejects
    any Commission carrying managed assets with
    `error_occurred(resolver_not_configured)` per spec/resolver/v0.1-beta/resolver.md §2.

    `AVP_RESOLVER_TOKEN`, when set, is used as a bearer token on every
    JSON-RPC request. Different supervisors can override the env var
    names by passing `url_env_var` / `token_env_var`; AVP doesn't
    constrain how the supervisor configures the agent's environment.
    """
    url = os.environ.get(url_env_var, "").strip()
    if not url:
        return None
    token = os.environ.get(token_env_var, "").strip() or None
    return HttpResolver(url=url, bearer_token=token, timeout_s=timeout_s)


__all__ = ["HttpResolver", "http_resolver_from_env"]
