"""Turn eval runs into what agentvoyagerproject.com renders.

Reduces a run's trajectories into the site's `{by_commission, commissions}`
payload and encodes it into the `…/view#z=<gzip+base64url>` link `avp eval view`
opens. The site owns the constellation rendering; this module just builds the
payload and the URL.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from avp.content import TextBlock
from avp.trajectory import (
    AgentStartedEvent,
    AgentStoppedEvent,
    AssistantMessageEvent,
    ErrorOccurredEvent,
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
    """Map one AVP event to the viz RunEvent shape (or None to drop it).

    Beyond the layout fields (type/step/tool/tokens) each event carries the
    detail the inspector shows: the model's text + per-turn cost, a tool's input
    and result preview, the run's final output, an error's message.
    """
    if isinstance(ev, AssistantMessageEvent):
        d = ev.data
        out: dict[str, Any] = {
            "seq": seq,
            "type": "model_turn_ended",
            "step": d.step,
            "tokens_in": d.usage.input_tokens,
            "tokens_out": d.usage.output_tokens,
            "cost_usd": d.cost_usd,
            "duration_ms": d.duration_ms,
        }
        text = _text_of(d.content)
        if text:
            out["text"] = _cap(text)
        if d.response_model:
            out["model"] = d.response_model
        return out
    if isinstance(ev, ToolInvokedEvent):
        d = ev.data
        out = {"seq": seq, "type": "tool_invoked", "step": d.step, "tool": d.tool_name}
        if d.tool_input:
            out["tool_input"] = _cap_obj(d.tool_input)
        if d.tool_dispatch_target:
            out["dispatch"] = d.tool_dispatch_target
        return out
    if isinstance(ev, ToolReturnedEvent):
        d = ev.data
        result = _result_text(d.tool_result)
        out = {
            "seq": seq,
            "type": "tool_returned",
            "step": d.step,
            "tool": d.tool_name,
            "duration_ms": d.duration_ms,
            "result_chars": len(result),
        }
        if result:
            out["result"] = _cap(result)
        if d.tool_result.is_error:
            out["is_error"] = True
        return out
    if isinstance(ev, AgentStartedEvent):
        return {"seq": seq, "type": "agent_started"}
    if isinstance(ev, AgentStoppedEvent):
        out = {"seq": seq, "type": "agent_stopped", "stop_reason": str(ev.data.reason)}
        if ev.data.output is not None:
            out["output"] = _cap(ev.data.output)
        return out
    if isinstance(ev, ErrorOccurredEvent):
        return {
            "seq": seq,
            "type": "error_occurred",
            "error_code": str(ev.data.error_code),
            "error_message": _cap(ev.data.error_message),
        }
    return None  # prelude (run_requested / agent_described) and custom events: skip


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
        "events": run_events,
    }


def run_from_ndjson(path: str | Path, *, score: float | None = None, passed: bool | None = None):
    """Parse an NDJSON trajectory file into a viz `Run`."""
    p = Path(path)
    events: list[BaseModel | dict[str, Any]] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(parse_event(json.loads(line)))
    return trajectory_to_run(events, run_id=p.stem, score=score, passed=passed)


# ── whole-eval payload for agentvoyagerproject.com ──────────────────────────


def _run_for_result(result: Any) -> dict[str, Any]:
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

    by_commission: dict[str, list[dict[str, Any]]] = {}
    for row in board.rows:
        by_commission[row.name] = [_run_for_result(r) for r in row.results]
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


# ── shareable viewer link (whole eval in the URL hash) ──────────────────────

SITE = "https://agentvoyagerproject.com"


def encode_payload(payload: dict[str, Any]) -> str:
    """gzip + base64url-encode a trajectories payload for the URL hash.

    The site's `/view` decodes this with `DecompressionStream('gzip')` after a
    base64url→base64 swap, so: gzip, then urlsafe-base64 (padding kept).
    """
    import base64
    import gzip

    raw = json.dumps(payload, separators=(",", ":")).encode()
    blob = gzip.compress(raw)
    return base64.urlsafe_b64encode(blob).decode()


def view_url(payload: dict[str, Any], *, site: str = SITE) -> str:
    """The `…/view#z=<gzip+base64url>` link the site renders the eval from."""
    return f"{site.rstrip('/')}/view#z={encode_payload(payload)}"
