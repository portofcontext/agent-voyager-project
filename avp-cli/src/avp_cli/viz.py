"""Turn eval runs into what agentvoyagerproject.com renders.

Reduces a run's trajectories into the site's `{by_commission, commissions}`
payload and uploads it for `avp eval share`, which prints the short `/r/<id>`
link. The site owns the rendering; this module builds the payload and talks to
the site's share API.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from avp.content import TextBlock
from avp.trajectory import (
    AgentDescribedEvent,
    AgentStartedEvent,
    AgentStoppedEvent,
    AssistantMessageEvent,
    ErrorOccurredEvent,
    RunRequestedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    parse_event,
)
from avp_cli.observability import Summary, summarize

# Per-event payloads can be huge (a tool result may carry a base64 PDF). Cap the
# rendered fields here so the whole eval still fits in a /view URL; the inspector
# shows what's kept and notes the overflow.
_CAP = 600
_CAP_INPUT = 400


def _cap(value: Any, n: int = _CAP) -> str:
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return s if len(s) <= n else f"{s[:n]}… (+{len(s) - n} chars)"


def _cap_obj(v: Any) -> Any:
    """Cap every string leaf of a value, preserving structure (for tool inputs)."""
    if isinstance(v, str):
        return _cap(v, _CAP_INPUT)
    if isinstance(v, list):
        return [_cap_obj(x) for x in v]
    if isinstance(v, dict):
        return {k: _cap_obj(x) for k, x in v.items()}
    return v


def _text_of(content: list[Any]) -> str:
    """Join the text of the TextBlocks in a message's content."""
    return "\n".join(b.text for b in content if isinstance(b, TextBlock) and b.text.strip())


def _result_text(result: Any) -> str:
    """The human-readable text of a ToolResultBlock (string or nested blocks)."""
    content = getattr(result, "content", "")
    if isinstance(content, str):
        return content
    parts = [getattr(b, "text", "") for b in content if getattr(b, "text", "")]
    return "\n".join(p for p in parts if p)


def _run_event(seq: int, ev: BaseModel) -> dict[str, Any] | None:
    """Project one AVP wire event onto the viz RunEvent (or None to drop it).

    The `type` is the event's real wire type (`avp.assistant_message`,
    `avp.tool_invoked`, ...) verbatim, and every field carries its wire
    attribute name (`input_tokens`, `tool_name`, `reason`). This is a thin
    projection, not a re-vocabulary: the only departures from a raw event dump
    are dropping the span/envelope plumbing and capping huge string leaves so
    the whole eval still fits in a /view URL (the inspector shows the cap).
    """
    if isinstance(ev, AssistantMessageEvent):
        d = ev.data
        out: dict[str, Any] = {
            "seq": seq,
            "type": ev.type,
            "step": d.step,
            "input_tokens": d.usage.input_tokens,
            "output_tokens": d.usage.output_tokens,
            "cost_usd": d.cost_usd,
            "duration_ms": d.duration_ms,
        }
        text = _text_of(d.content)
        if text:
            out["text"] = _cap(text)
        if d.response_model:
            out["response_model"] = d.response_model
        return out
    if isinstance(ev, ToolInvokedEvent):
        d = ev.data
        out = {
            "seq": seq,
            "type": ev.type,
            "step": d.step,
            "tool_name": d.tool_name,
            "call_id": d.tool_call_id,
        }
        if d.tool_input:
            out["tool_input"] = _cap_obj(d.tool_input)
        if d.tool_dispatch_target:
            out["tool_dispatch_target"] = d.tool_dispatch_target
        return out
    if isinstance(ev, ToolReturnedEvent):
        d = ev.data
        result = _result_text(d.tool_result)
        out = {
            "seq": seq,
            "type": ev.type,
            "step": d.step,
            "tool_name": d.tool_name,
            "call_id": d.tool_call_id,
            "duration_ms": d.duration_ms,
            "result_chars": len(result),
        }
        if result:
            out["result"] = _cap(result)
        if d.tool_result.is_error:
            out["is_error"] = True
        return out
    if isinstance(ev, AgentStartedEvent):
        return {"seq": seq, "type": ev.type}
    if isinstance(ev, AgentStoppedEvent):
        out = {"seq": seq, "type": ev.type, "reason": str(ev.data.reason)}
        if ev.data.output is not None:
            out["output"] = _cap(ev.data.output)
        return out
    if isinstance(ev, ErrorOccurredEvent):
        return {
            "seq": seq,
            "type": ev.type,
            "error_code": str(ev.data.error_code),
            "error_message": _cap(ev.data.error_message),
        }
    return None  # prelude (run_requested / agent_described) and custom events: skip


def _trim(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[:n].rstrip() + "…"


def _params(schema: Any) -> list[dict[str, Any]]:
    """A JSON Schema's top-level parameters: name, type, required, description."""
    if not isinstance(schema, dict):
        return []
    props = schema.get("properties")
    if not isinstance(props, dict):
        return []
    required = set(schema.get("required") or [])
    out = []
    for name, spec in props.items():
        spec = spec if isinstance(spec, dict) else {}
        param: dict[str, Any] = {"name": name, "required": name in required}
        kind = spec.get("type")
        if isinstance(kind, list):
            kind = " | ".join(str(k) for k in kind)
        if kind:
            param["type"] = str(kind)
        if spec.get("description"):
            param["description"] = _trim(str(spec["description"]), 240)
        out.append(param)
    return out


def _decl(d: Any, fallback: Any = None) -> dict[str, Any]:
    """A tool / subagent / skill declaration: name, description, parameters, and
    MCP server. Detail missing from the run's snapshot is taken from the agent's
    descriptor entry of the same name (`fallback`)."""
    out: dict[str, Any] = {"name": d.name}
    desc = getattr(d, "description", None) or getattr(fallback, "description", None)
    if desc:
        out["description"] = _trim(desc, 1200)
    params = _params(getattr(d, "inputSchema", None) or getattr(fallback, "inputSchema", None))
    if params:
        out["params"] = params
    server = getattr(d, "mcp_server_id", None)
    if server:
        out["mcp_server_id"] = server
    return out


def _brief(events: list[BaseModel | dict[str, Any]]) -> dict[str, Any]:
    """The run's `vessel` (the agent and everything it could use) and `orders`
    (what it was asked to do), from the trajectory's opening events.

    `agent_started` is AVP's merged snapshot of what this run could actually
    use (tools offered after allow-lists, connected MCP servers, skills,
    subagents) and the prompt as given; `agent_described` names the agent;
    `run_requested` carries the Commission's rules.
    """
    requested = next((e for e in events if isinstance(e, RunRequestedEvent)), None)
    described = next((e for e in events if isinstance(e, AgentDescribedEvent)), None)
    started = next((e for e in events if isinstance(e, AgentStartedEvent)), None)
    commission = requested.data.commission if requested else None
    descriptor = described.data.descriptor if described else None
    s = started.data if started else None
    described_tools = {t.name: t for t in (descriptor.tools or [])} if descriptor else {}
    vessel: dict[str, Any] = {
        "agent": descriptor.agent_name if descriptor else None,
        "version": descriptor.agent_version if descriptor else None,
        "model": (s.request_model if s else None) or (commission.model if commission else None),
        "tools": [
            _decl(t, described_tools.get(t.name)) for t in (s.tools if s and s.tools else [])
        ],
        "subagents": [_decl(x) for x in (s.subagents if s and s.subagents else [])],
        "skills": [_decl(x) for x in (s.skills if s and s.skills else [])],
        "mcp_servers": [
            {"id": m.id, "status": m.status} for m in (s.mcp_servers if s and s.mcp_servers else [])
        ],
    }
    orders: dict[str, Any] = {
        "task": _cap(
            (s.prompt if s else None) or (commission.prompt if commission else "") or "", 4000
        ),
        "system_prompt": _cap(s.system_prompt, 2000) if s and s.system_prompt else None,
    }
    if commission is not None and commission.enabled_builtin_tools is not None:
        orders["allowed_tools"] = commission.enabled_builtin_tools
    return {
        "vessel": {k: v for k, v in vessel.items() if v not in (None, [])},
        "orders": {k: v for k, v in orders.items() if v not in (None, "", {})},
    }


def trajectory_to_run(
    events: list[BaseModel | dict[str, Any]],
    *,
    run_id: str,
    score: float | None = None,
    passed: bool | None = None,
) -> dict[str, Any]:
    """Build the viz `Run` from parsed trajectory events."""
    summary: Summary = summarize(events)
    run_events: list[dict[str, Any]] = []
    for ev in events:
        if isinstance(ev, BaseModel):
            re = _run_event(len(run_events), ev)
            if re is not None:
                run_events.append(re)
    return {
        "row_id": run_id,
        "run_id": run_id,
        "passed": passed,
        "score": score,
        "stop_reason": summary.stop_reason,
        "total_cost_usd": summary.total_cost_usd,
        "total_turns": summary.total_turns,
        "total_tokens": summary.total_tokens,
        "elapsed_s": summary.duration_ms / 1000 if summary.duration_ms else None,
        **_brief(events),
        "events": run_events,
    }


def _parse_ndjson(path: Path) -> list[BaseModel | dict[str, Any]]:
    return [parse_event(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def run_from_ndjson(path: str | Path, *, score: float | None = None, passed: bool | None = None):
    """Parse an NDJSON trajectory file into a viz `Run`."""
    p = Path(path)
    return trajectory_to_run(_parse_ndjson(p), run_id=p.stem, score=score, passed=passed)


# ── whole-eval payload for agentvoyagerproject.com ──────────────────────────


def _item_fields(item: Any) -> dict[str, Any]:
    """The dataset item's question and expected answer, for the share page."""
    out: dict[str, Any] = {"question": _cap(item.prompt, 4000)}
    if item.expected is not None:
        out["expected"] = _cap(item.expected, 2000)
    return out


def _run_for_result(result: Any, item: Any = None) -> dict[str, Any]:
    """Build the site's per-run shape from a RunResult (reading its trajectory)."""
    run_id = f"{result.setup_name}-{result.item_id}"
    if result.trajectory_path and Path(result.trajectory_path).is_file():
        run = run_from_ndjson(
            result.trajectory_path,
            score=result.score.value if result.score else None,
            passed=result.passed if result.score else None,
        )
        run["row_id"] = result.item_id
        run["run_id"] = run_id
        if item is not None:
            run.update(_item_fields(item))
        if result.score and result.score.detail:
            run["verdict"] = _cap(result.score.detail, 2000)
        return run
    # spawn error / no trajectory: a minimal placeholder run
    return {
        "row_id": result.item_id,
        "run_id": run_id,
        "passed": False,
        "score": None,
        "stop_reason": "error",
        "total_cost_usd": None,
        "total_turns": None,
        "total_tokens": None,
        "elapsed_s": None,
        "events": [],
    }


def _mcp_meta(m: Any) -> dict[str, Any]:
    """MCP server detail for the payload, WITHOUT secrets (no headers / env)."""
    d: dict[str, Any] = {"id": m.id, "type": m.type}
    if getattr(m, "url", None):
        d["url"] = m.url
    if getattr(m, "command", None):
        d["command"] = m.command
    return d


def _commission_meta(setup: Any) -> dict[str, Any]:
    """The base wire Commission's config for the 'what varied' cards on /view.

    Reads the commission's real fields (the `prompt` may carry the `{input}`
    placeholder), carrying skill + MCP *identities* only — never skill file bodies
    or MCP auth, since the payload may travel in a URL."""
    c = setup.commission
    meta: dict[str, Any] = {
        "model": c.model,
        "system_prompt": c.system_prompt,
        "prompt": c.prompt,
        "enabled_builtin_tools": c.enabled_builtin_tools,
        "output_schema": c.output_schema,
    }
    if c.skills:
        meta["skills"] = [{"id": s.id, "name": getattr(s, "name", None)} for s in c.skills]
    if c.mcp_servers:
        meta["mcp_servers"] = [_mcp_meta(m) for m in c.mcp_servers]
    return {k: v for k, v in meta.items() if v not in (None, [], {})}


def to_trajectories_payload(board: Any, *, eval_version: str, ev: Any = None) -> dict[str, Any]:
    """Build the `{eval_version, snapshot_at, by_commission, commissions}` payload the site renders.

    `by_commission` is keyed by commission name; each value is the list of that
    commission's runs in the site's per-run shape. When `ev` (the Eval) is given,
    `commissions` carries each commission's config (prompt, tools, skills, MCP,
    output_schema) so /view can show what varied. One payload per agent.
    """
    from datetime import datetime

    items = {str(i.id): i for i in ev.dataset} if ev is not None else {}
    by_commission: dict[str, list[dict[str, Any]]] = {}
    for row in board.rows:
        by_commission[row.name] = [
            _run_for_result(r, items.get(str(r.item_id))) for r in row.results
        ]
    payload: dict[str, Any] = {
        "eval_version": eval_version,
        "snapshot_at": datetime.now(UTC).isoformat(),
        "agent": board.agent_label,
        "by_commission": by_commission,
    }
    if ev is not None:
        # Only this agent's commissions: a commission bound to another agent
        # isn't part of this board.
        from avp_cli.eval.engine import setups_for

        payload["commissions"] = {
            s.id: _commission_meta(s) for s in setups_for(ev.setups, board.agent_label)
        }
    return payload


def enrich_payload(payload: dict[str, Any], run_dir: Path, eval_config: dict | None) -> None:
    """Fill in what a run recorded before payloads carried it: the vessel,
    orders, and events with tool call ids (rebuilt from each run's NDJSON
    trajectory next to the payload), and the question and expected answer
    (from the run's inline dataset). In place."""
    items = {
        str(i.get("id")): i
        for i in (((eval_config or {}).get("dataset") or {}).get("items") or [])
        if isinstance(i, dict)
    }
    slices = payload["agents"] if isinstance(payload.get("agents"), list) else [payload]
    for agent in slices:
        for runs in (agent.get("by_commission") or {}).values():
            for run in runs:
                ndjson = run_dir / f"{agent.get('agent')}-{run.get('run_id')}.ndjson"
                if "vessel" not in run and ndjson.is_file():
                    fresh = trajectory_to_run(_parse_ndjson(ndjson), run_id=str(run.get("run_id")))
                    run.update({k: fresh[k] for k in ("vessel", "orders", "events") if k in fresh})
                item = items.get(str(run.get("row_id")))
                if item is not None and "question" not in run:
                    run["question"] = _cap(item.get("prompt", ""), 4000)
                    if item.get("expected") is not None:
                        run["expected"] = _cap(item["expected"], 2000)


def combine_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold per-agent payloads into one multi-agent payload for a single /view link.

    `{eval_version, snapshot_at, agents: [<per-agent payload>, ...]}` — the site
    renders all agents on one page (head-to-head). A single-agent eval keeps its
    flat shape (no `agents` wrapper) so the common case stays simple.
    """
    if len(payloads) == 1:
        return payloads[0]
    return {
        "eval_version": payloads[0].get("eval_version"),
        "snapshot_at": payloads[0].get("snapshot_at"),
        "agents": payloads,
    }


# ── shared links (`avp eval share`) ──────────────────────────────────────────

SITE = "https://www.agentvoyagerproject.com"


class ShareError(Exception):
    """The site refused or failed a share request."""


def encode_payload(payload: dict[str, Any]) -> str:
    """gzip + base64url-encode a trajectories payload for upload.

    The site decodes it with `DecompressionStream('gzip')` after a
    base64url→base64 swap, so: gzip, then urlsafe-base64 (padding kept).
    """
    import base64
    import gzip

    raw = json.dumps(payload, separators=(",", ":")).encode()
    blob = gzip.compress(raw)
    return base64.urlsafe_b64encode(blob).decode()


def _request(method: str, url: str, *, body: bytes | None = None, token: str | None = None):
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("user-agent", "avp-cli")
    if body is not None:
        req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            return resp.status, json.loads(data) if data else None
    except urllib.error.HTTPError as err:
        if err.code == 429:
            raise ShareError(
                "too many shares from this network; try again in a few minutes"
            ) from None
        try:
            detail = json.loads(err.read()).get("error")
        except Exception:
            detail = None
        if isinstance(detail, dict):  # Vercel's own errors nest a message
            detail = detail.get("message")
        raise ShareError(detail or f"HTTP {err.code}") from None
    except urllib.error.URLError as err:
        raise ShareError(f"could not reach {url}: {err.reason}") from None


def share(payload: dict[str, Any], *, site: str = SITE) -> dict[str, Any]:
    """Upload a run; returns `{id, url, delete_token, expires_at}`."""
    body = json.dumps({"z": encode_payload(payload)}).encode()
    _, data = _request("POST", f"{site.rstrip('/')}/api/runs", body=body)
    return data


def unshare(share_id: str, delete_token: str, *, site: str = SITE) -> None:
    """Take a shared run down."""
    _request("DELETE", f"{site.rstrip('/')}/api/runs/{share_id}", token=delete_token)
