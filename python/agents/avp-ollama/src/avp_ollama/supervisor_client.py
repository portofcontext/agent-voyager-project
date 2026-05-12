"""HTTP client for the supervisor's event-append API.

Minimal subset — `avp-ollama` only needs to POST events. State transitions
(running/completed/failed) are inferred by the supervisor from the
`agent_started` / `agent_stopped` events the translator emits.

Synchronous httpx; the translator runs on a worker thread launched by the
FastAPI dispatcher, so async would just complicate the call chain without
buying us anything for the rescue demo."""

from __future__ import annotations

import os
from typing import Any

import httpx


class SupervisorEventClient:
    """POSTs events to `{base_url}/api/runs/{run_id}/events`.

    Pulls `SUPERVISOR_BASE_URL` and the optional `SUPERVISOR_PROXY_TOKEN`
    from env when not given explicitly."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base = (
            base_url or os.environ.get("SUPERVISOR_BASE_URL") or "http://localhost:5150"
        ).rstrip("/")
        headers: dict[str, str] = {}
        tok = token if token is not None else os.environ.get("SUPERVISOR_PROXY_TOKEN")
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        self._client = httpx.Client(timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SupervisorEventClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def append_event(self, run_id: str, seq: int, event: dict[str, Any]) -> dict[str, Any]:
        """Append one CloudEvents-shaped event. Raises `httpx.HTTPStatusError`
        on non-2xx (the translator catches and logs; a failed event post
        should not abort the run)."""
        r = self._client.post(
            f"{self._base}/api/runs/{run_id}/events",
            json={"seq": seq, "event": event},
        )
        r.raise_for_status()
        return r.json()

    def fetch_events(self, run_id: str) -> list[dict[str, Any]]:
        """Return every event the supervisor has for `run_id`, in
        seq order. Used by the translator to discover the next free
        seq on startup (which is non-zero when this run was rescued
        and is being resumed by a fresh runner)."""
        r = self._client.get(f"{self._base}/api/runs/{run_id}/events")
        r.raise_for_status()
        body = r.json()
        return body if isinstance(body, list) else []

    def next_seq(self, run_id: str) -> int:
        """Return `max(seq) + 1` over the run's existing events.
        Zero for a fresh dispatch with no prior events."""
        events = self.fetch_events(run_id)
        if not events:
            return 0
        return max(int(e.get("seq", 0)) for e in events) + 1
