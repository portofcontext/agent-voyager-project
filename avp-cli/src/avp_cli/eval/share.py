"""Sharing an eval on agentvoyagerproject.com: its results and Trajectories,
reduced to what the site's viewer shows, and uploaded for a link that lasts 30
days. The site owns the page; this builds its payload and calls its API."""

import base64
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, JsonValue, ValidationError

from avp.artifacts import artifact_path, read_artifacts
from avp.commission import Commission
from avp.trajectory import Trajectory, avp_metadata, documents, final_output
from avp_cli import paths
from avp_cli.console import Failed
from avp_cli.eval.results import EvalResults, RunResult
from avp_cli.eval.schemas import Eval, Item
from avp_cli.eval.scoring import read_trajectory
from avp_cli.eval.template import TemplateError, render

SITE = "https://www.agentvoyagerproject.com"
TEXT = 600
"""The characters kept of a message, a tool result, or an output. A tool
result can be a whole file, and the site refuses a large upload."""
INPUT = 400
"""The characters kept of each string in a tool's input."""
PROMPT = 4000
SYSTEM_PROMPT = 2000


class Shared(BaseModel):
    """`share.json` in the eval's directory: where the eval is shared, and the
    token that takes it down."""

    id: str
    url: str
    delete_token: str
    expires_at: datetime
    site: str


def _duration(call, result):
    """Elapsed time between SDK observations, including dispatch/reporting delays."""
    started = avp_metadata(call).get("observed_at") if call else None
    finished = avp_metadata(result).get("finished_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        return None
    try:
        return max(
            0,
            round(
                (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
                * 1000
            ),
        )
    except (ValueError, TypeError):
        return None


def _cut(value: Any, limit: int = TEXT) -> str:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, default=lambda v: v.model_dump(mode="json", exclude_none=True))
    )
    return text if len(text) <= limit else f"{text[:limit]}… (+{len(text) - limit} chars)"


def _cut_strings(value: JsonValue) -> JsonValue:
    if isinstance(value, str):
        return _cut(value, INPUT)
    if isinstance(value, list):
        return [_cut_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: _cut_strings(v) for k, v in value.items()}
    return value


def _presentation(trajectory: Trajectory | None) -> list[dict[str, Any]]:
    """Cards for the hosted site's presentation API, derived from ATIF.

    These are truncated display cards, not a second persisted trajectory.
    """
    shown = []

    def card(kind, **fields):
        shown.append(
            {
                "seq": len(shown),
                "type": f"avp.{kind}",
                **{k: v for k, v in fields.items() if v is not None},
            }
        )

    if trajectory is None:
        return shown
    card("agent_started")
    for doc in documents(trajectory):
        for step in doc.steps:
            if step.source == "agent":
                usage = step.metrics
                card(
                    "assistant_message",
                    text=_cut(step.message),
                    input_tokens=usage.prompt_tokens if usage else None,
                    output_tokens=usage.completion_tokens if usage else None,
                    cost_usd=usage.cost_usd if usage else None,
                    duration_ms=avp_metadata(step).get("duration_ms"),
                    response_model=step.model_name or doc.agent.model_name,
                )
            if code := avp_metadata(step).get("error_code"):
                card("error_occurred", error_code=code, error_message=_cut(step.message))
            calls = {c.tool_call_id: c for c in step.tool_calls or []}
            for call in calls.values():
                card(
                    "tool_invoked",
                    tool_name=call.function_name,
                    call_id=call.tool_call_id,
                    tool_input=_cut_strings(call.arguments),
                )
            for result in step.observation.results if step.observation else []:
                call = calls.get(result.source_call_id)
                card(
                    "tool_returned",
                    tool_name=call.function_name if call else "delegation",
                    call_id=result.source_call_id,
                    duration_ms=_duration(call, result),
                    result=_cut(result.content),
                    is_error=avp_metadata(result).get("is_error"),
                    result_chars=len(result.content) if isinstance(result.content, str) else None,
                )
    meta = avp_metadata(trajectory)
    if meta.get("complete"):
        card(
            "agent_stopped",
            reason=meta.get("stop_reason"),
            output=_cut(output) if (output := final_output(trajectory)) is not None else None,
        )
    return shown


def _brief(
    trajectory: Trajectory | None, effective: dict[str, Any] | None = None
) -> dict[str, Any]:
    if trajectory is None:
        return {}
    agent = trajectory.agent
    extra = (agent.extra or {}).get("avp", {})
    if effective is not None:
        extra = {**effective, **effective.get("model", {}), **extra}
    catalog = {t["name"]: t for t in (effective or {}).get("tools", [])}
    tools = []
    for definition in agent.tool_definitions or []:
        function = definition.get("function", {})
        parameters = function.get("parameters", {})
        params = [
            {
                "name": name,
                "required": name in parameters.get("required", []),
                **{k: value[k] for k in ("type", "description") if k in value},
            }
            for name, value in parameters.get("properties", {}).items()
        ]
        tools.append(
            {
                k: v
                for k, v in {
                    "name": function.get("name"),
                    "description": _cut(function.get("description", ""), 1200),
                    "params": params or None,
                    "mcp_server_id": catalog.get(function.get("name"), {}).get("mcp_server_id"),
                }.items()
                if v is not None
            }
        )
    model = agent.model_name
    if model and extra.get("provider"):
        model = f"{extra['provider']}/{model}"
    vessel = {
        "agent": agent.name,
        "version": agent.version,
        "model": model,
        "tools": tools,
        **{k: extra[k] for k in ("subagents", "skills", "mcp_servers") if k in extra},
    }
    prompts = {
        s.source: s.message
        for s in trajectory.steps
        if s.source in ("user", "system") and not avp_metadata(s).get("error_code")
    }
    orders = {
        "task": _cut(prompts.get("user", ""), PROMPT),
        "system_prompt": _cut(prompts["system"], SYSTEM_PROMPT) if "system" in prompts else None,
    }
    return {
        "vessel": {k: v for k, v in vessel.items() if v not in (None, [])},
        "orders": {k: v for k, v in orders.items() if v is not None},
    }


def _commission(directory: Path) -> Commission | None:
    try:
        return Commission.model_validate_json((directory / paths.COMMISSION).read_text())
    except (OSError, ValidationError):
        return None


def _expected(eval: Eval | None, item: Item | None) -> str | None:
    """The scorer's `expected`, filled from the item, when it has one that
    fills from the item alone."""
    expected = eval.scorer.config.get("expected") if eval else None
    if not isinstance(expected, str) or item is None:
        return None
    try:
        filled = render(expected, {"item": item.model_dump(mode="json")}, "scorer.expected")
    except TemplateError:
        return None
    return _cut(filled, SYSTEM_PROMPT) if isinstance(filled, str) else None


def _run(run: RunResult, directory: Path, eval: Eval | None, item: Item | None) -> dict[str, Any]:
    trajectory, _ = read_trajectory(directory / run.directory / paths.TRAJECTORY)
    commission = _commission(directory / run.directory)
    shown = _presentation(trajectory)
    effective = None
    run_directory = directory / run.directory
    if (run_directory / paths.ARTIFACTS).exists():
        try:
            manifest = read_artifacts(run_directory, run_id=run.run_id)
            if any(
                a.path == "inputs/effective-agent.json" and a.role == "input"
                for a in manifest.artifacts
            ):
                effective = json.loads(
                    artifact_path(run_directory, "inputs/effective-agent.json").read_text()
                )
        except (OSError, ValueError) as exc:
            raise Failed(f"invalid run artifacts: {exc}") from None
    verdict = run.scorer_error or "; ".join(run.score.reasons if run.score else [])
    return {
        "row_id": run.item,
        "run_id": run.run_id,
        "passed": run.score.passed if run.score else None,
        "score": run.score.value if run.score else None,
        "stop_reason": run.reason,
        "total_cost_usd": run.totals.cost_usd
        if trajectory and "cost_usd" not in run.totals.unknown_metrics
        else None,
        "total_turns": run.totals.turns if trajectory else None,
        "total_tokens": run.totals.input_tokens + run.totals.output_tokens
        if trajectory
        and not {"input_tokens", "output_tokens"}.intersection(run.totals.unknown_metrics)
        else None,
        "elapsed_s": run.seconds,
        **_brief(trajectory, effective),
        **({"question": _cut(commission.prompt, PROMPT)} if commission else {}),
        **({"expected": expected} if (expected := _expected(eval, item)) else {}),
        **({"verdict": _cut(verdict, SYSTEM_PROMPT)} if verdict else {}),
        "events": shown,
    }


def _settings(commission: Commission) -> dict[str, Any]:
    """What the Commission configures, for the site's "what varied" cards. No
    credential, header, environment, or skill file is included."""
    shown = {
        "model": f"{commission.model.provider}/{commission.model.id}",
        "system_prompt": commission.system_prompt,
        "prompt": commission.prompt,
        "output_schema": commission.output_schema,
        "skills": [{"id": s.name, "name": s.name} for s in commission.skills or []],
        "mcp_servers": [
            {k: v for k, v in m.model_dump(mode="json").items() if k in ("id", "type", "url")}
            | ({"command": m.command[:1]} if m.type == "stdio" else {})
            for m in commission.mcp_servers or []
        ],
    }
    return {k: v for k, v in shown.items() if v not in (None, [])}


def payload(directory: Path, results: EvalResults) -> dict[str, Any]:
    """The eval as the site reads it: one slice per agent, each with its runs
    by Commission. An eval of one agent is that slice alone."""
    try:
        eval = Eval.model_validate_json((directory / paths.EVAL).read_text())
    except (OSError, ValidationError):
        eval = None
    items = {item.id: item for item in eval.dataset} if eval else {}
    slices = []
    for agent in dict.fromkeys(run.agent for run in results.runs):
        by_commission: dict[str, list[dict[str, Any]]] = {}
        commissions: dict[str, dict[str, Any]] = {}
        for run in results.of(agent=agent):
            by_commission.setdefault(run.commission, []).append(
                _run(run, directory, eval, items.get(run.item))
            )
            if run.commission not in commissions and (
                commission := _commission(directory / run.directory)
            ):
                commissions[run.commission] = _settings(commission)
        slices.append({"agent": agent, "by_commission": by_commission, "commissions": commissions})
    if not slices:
        raise Failed(f"{results.id} has no runs to share")
    top = {
        "name": results.name,
        "eval_version": "0.1",
        "snapshot_at": datetime.now(UTC).isoformat(),
    }
    return top | (slices[0] if len(slices) == 1 else {"agents": slices})


def encode(payload: dict[str, Any]) -> str:
    """The upload's `z`: the payload as JSON, gzipped, then base64url with its
    padding, which the site reverses."""
    compact = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(gzip.compress(compact)).decode()


def _request(
    method: str, url: str, body: dict[str, Any] | None = None, token: str | None = None
) -> httpx.Response:
    headers = {"user-agent": "avp-cli"} | ({"authorization": f"Bearer {token}"} if token else {})
    try:
        response = httpx.request(method, url, json=body, headers=headers, timeout=60)
    except httpx.HTTPError as error:
        raise Failed(f"couldn't reach {url}: {error}") from None
    if response.status_code == 429:
        raise Failed("too many shares from this network; try again in a few minutes")
    if response.is_error:
        try:
            why = response.json().get("error")
        except ValueError:
            why = None
        if isinstance(why, dict):
            why = why.get("message")
        raise Failed(f"{url} refused: {why or f'HTTP {response.status_code}'}")
    return response


def share(directory: Path, results: EvalResults, site: str = SITE) -> Shared:
    """Upload the eval and keep where it is shared in its directory."""
    site = site.rstrip("/")
    body = {"z": encode(payload(directory, results))}
    answer = _request("POST", f"{site}/api/runs", body).json()
    try:
        shared = Shared(site=site, **answer)
    except (TypeError, ValidationError):
        raise Failed(f"{site} answered without a link") from None
    (directory / paths.SHARE).write_text(shared.model_dump_json(indent=2) + "\n")
    return shared


def shared(directory: Path) -> Shared | None:
    """Where the eval is shared, when it is."""
    try:
        return Shared.model_validate_json((directory / paths.SHARE).read_text())
    except (OSError, ValidationError):
        return None


def unshare(directory: Path) -> Shared:
    """Take the eval's link down and forget it."""
    found = shared(directory)
    if found is None:
        raise Failed(f"{directory.name} isn't shared")
    try:
        _request("DELETE", f"{found.site}/api/runs/{found.id}", token=found.delete_token)
    finally:
        (directory / paths.SHARE).unlink(missing_ok=True)
    return found
