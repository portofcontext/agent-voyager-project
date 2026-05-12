"""FastAPI dispatcher for the avp-ollama runner.

Mirrors the shape `worker/modal_app.py::spawn_endpoint` uses, so the
supervisor's `LocalOllamaBackend` can talk to either backend without
caring which is on the other end.

Body: `{run_id, environment?, resolver?}`. The supervisor has already
created the Run row in Postgres; this endpoint just kicks off the
`OllamaTranslator` on a background thread and returns immediately.

Run as `avp-ollama-runner` (entry point). The Run config is fetched
from the supervisor on dispatch — the supervisor stores the
Commission alongside the row.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException

from .supervisor_client import SupervisorEventClient
from .translator import OllamaTranslator, RescueFailAt

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="avp-ollama runner")


def _fetch_run_config(run_id: str) -> dict[str, Any]:
    base = (os.environ.get("SUPERVISOR_BASE_URL") or "http://localhost:5150").rstrip("/")
    headers: dict[str, str] = {}
    if tok := os.environ.get("SUPERVISOR_PROXY_TOKEN"):
        headers["Authorization"] = f"Bearer {tok}"
    r = httpx.get(f"{base}/api/runs/{run_id}", headers=headers, timeout=30.0)
    r.raise_for_status()
    body = r.json()
    config = body.get("config")
    if not isinstance(config, dict):
        raise ValueError(f"supervisor returned no config for {run_id}")
    return config


def _drive_run(run_id: str) -> None:
    """Background thread target. Fetches the run config, drives the
    translator. Exceptions are logged; the supervisor will surface a
    rescue-able state via the `execution_backend_failure` event the
    translator emits before re-raising."""
    logger.info("driving run %s", run_id)
    try:
        config = _fetch_run_config(run_id)
    except Exception:
        logger.exception("failed to fetch run config for %s", run_id)
        return
    client = SupervisorEventClient()
    try:
        translator = OllamaTranslator(run_id=run_id, config=config, client=client)
        outcome = translator.run()
        logger.info("run %s finished: %s", run_id, outcome)
    finally:
        client.close()


@app.post("/")
def spawn(payload: dict[str, Any]) -> dict[str, Any]:
    """Supervisor-facing dispatch webhook. Matches `LocalOllamaBackend`'s
    request body."""
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise HTTPException(status_code=400, detail="missing_run_id")
    # Log injection-mode if set — useful when debugging a smoke test.
    fail = RescueFailAt.from_env()
    if fail.mode != "none":
        logger.info(
            "dispatch %s with RESCUE_FAIL_AT=%s (turn=%s, prob=%s)",
            run_id, fail.mode, fail.turn, fail.probability,
        )
    thread = threading.Thread(target=_drive_run, args=(run_id,), daemon=True)
    thread.start()
    return {"run_id": run_id, "call_id": run_id, "status": "spawned"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    port = int(os.environ.get("OLLAMA_RUNNER_PORT") or 8081)
    host = os.environ.get("OLLAMA_RUNNER_HOST") or "0.0.0.0"
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
