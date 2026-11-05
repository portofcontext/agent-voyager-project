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

from avp.commission import Commission
from avp.trajectory import (
    AgentDescribedEvent,
    AgentStartedEvent,
    AgentStoppedEvent,
    AssistantMessageEvent,
    ErrorOccurredEvent,
    Event,
    TextBlock,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
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


def _cut(value: JsonValue, limit: int = TEXT) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else f"{text[:limit]}… (+{len(text) - limit} chars)"


def _cut_strings(value: JsonValue) -> JsonValue:
    if isinstance(value, str):
        return _cut(value, INPUT)
    if isinstance(value, list):
        return [_cut_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: _cut_strings(v) for k, v in value.items()}
    return value


def _event(seq: int, event: Event) -> dict[str, Any] | None:
    """The event as the site's viewer reads it: its type with the `avp.`
    prefix, and its fields flat. None for an event the viewer doesn't show."""
    shown: dict[str, Any] = {"seq": seq, "type": f"avp.{event.type}"}
    match event:
        case AssistantMessageEvent(data=data):
            text = "\n".join(
                b.text for b in data.content if isinstance(b, TextBlock) and b.text.strip()
            )
            shown |= {
                "input_tokens": data.usage.input_tokens,
                "output_tokens": data.usage.output_tokens,
                "cost_usd": data.usage.cost_usd,
                "duration_ms": data.duration_ms,
                "text": _cut(text) if text else None,
                "response_model": data.response_model,
            }
        case ToolInvokedEvent(data=data):
            shown |= {
                "tool_name": data.tool_name,
                "call_id": data.tool_call_id,
                "tool_input": _cut_strings(data.tool_input) if data.tool_input else None,
            }
        case ToolReturnedEvent(data=data):
            content = data.tool_result.content
            result = (
                content
                if isinstance(content, str)
                else "\n".join(b.text for b in content if isinstance(b, TextBlock) and b.text)
            )
            shown |= {
                "tool_name": data.tool_name,
                "call_id": data.tool_call_id,
                "duration_ms": data.duration_ms,
                "result_chars": len(result),
                "result": _cut(result) if result else None,
                "is_error": True if data.tool_result.is_error else None,
            }
        case AgentStartedEvent():
            pass
        case AgentStoppedEvent(data=data):
            shown |= {
                "reason": data.reason,
                "output": None if data.output is None else _cut(data.output),
            }
        case ErrorOccurredEvent(data=data):
            shown |= {"error_code": data.error_code, "error_message": _cut(data.error_message)}
        case _:
            return None
    return {k: v for k, v in shown.items() if v is not None}


def _parameters(schema: JsonValue) -> list[dict[str, Any]]:
    """A tool's top-level parameters, from its input schema."""
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        return []
    required = schema.get("required") if isinstance(schema, dict) else None
    found = []
    for name, spec in properties.items():
        spec = spec if isinstance(spec, dict) else {}
        kind = spec.get("type")
        found.append(
            {
                "name": name,
                "required": isinstance(required, list) and name in required,
                "type": " | ".join(map(str, kind)) if isinstance(kind, list) else kind,
                "description": _cut(spec["description"], 240) if spec.get("description") else None,
            }
        )
    return [{k: v for k, v in p.items() if v is not None} for p in found]


def _declared(item: Any) -> dict[str, Any]:
    """A tool, subagent, or skill the run had: its name and what describes it."""
    shown = {
        "name": item.name,
        "description": _cut(item.description, 1200) if item.description else None,
        "params": _parameters(getattr(item, "input_schema", None)) or None,
        "mcp_server_id": getattr(item, "mcp_server_id", None),
    }
    return {k: v for k, v in shown.items() if v is not None}


def _brief(events: list[Event]) -> dict[str, Any]:
    """The run's `vessel`, the agent and what it had, and `orders`, what it
    was asked: from `agent_described` and `agent_started`."""
    described = next((e.data for e in events if isinstance(e, AgentDescribedEvent)), None)
    started = next((e.data for e in events if isinstance(e, AgentStartedEvent)), None)
    if started is None:
        return {}
    vessel = {
        "agent": described.descriptor.agent_name if described else None,
        "version": described.descriptor.agent_version if described else None,
        "model": f"{started.model.provider}/{started.model.id}",
        "tools": [_declared(t) for t in started.tools or []],
        "subagents": [_declared(s) for s in started.subagents or []],
        "skills": [_declared(s) for s in started.skills or []],
        "mcp_servers": [
            {"id": m.id} | ({"status": m.status} if m.status else {})
            for m in started.mcp_servers or []
        ],
    }
    orders = {
        "task": _cut(started.prompt, PROMPT),
        "system_prompt": _cut(started.system_prompt, SYSTEM_PROMPT)
        if started.system_prompt
        else None,
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
    events, _ = read_trajectory(directory / run.directory / paths.TRAJECTORY)
    commission = _commission(directory / run.directory)
    shown: list[dict[str, Any]] = []
    for event in events:
        if projected := _event(len(shown), event):
            shown.append(projected)
    verdict = run.scorer_error or "; ".join(run.score.reasons if run.score else [])
    return {
        "row_id": run.item,
        "run_id": run.run_id,
        "passed": run.score.passed if run.score else None,
        "score": run.score.value if run.score else None,
        "stop_reason": run.reason,
        "total_cost_usd": run.totals.cost_usd if events else None,
        "total_turns": run.totals.turns if events else None,
        "total_tokens": run.totals.input_tokens + run.totals.output_tokens if events else None,
        "elapsed_s": run.seconds,
        **_brief(events),
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
