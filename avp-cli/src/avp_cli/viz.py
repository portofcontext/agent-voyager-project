"""Visualize an AVP trajectory as a constellation, the agentvoyagerproject.com way.

Turns a raw NDJSON trajectory into the `Run` shape the site's
`TrajectoryConstellation` consumes, then writes a self-contained HTML file (the
constellation SVG + reveal animation ported to vanilla JS, brand palette) you
open in a browser. No server, no network.
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
from avp_cli import brand
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


def render_html(run: dict[str, Any]) -> str:
    """A self-contained HTML constellation for one run."""
    return _TEMPLATE.replace("__RUN_JSON__", json.dumps(run))


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
        payload["commissions"] = {s.id: _commission_meta(s) for s in ev.setups}
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


# ── terminal view ──────────────────────────────────────────────────────────

_TERM_COLOR = {
    "agent_started": brand.SKY,
    "agent_stopped": brand.SKY,
    "model_turn_ended": brand.MAST,
    "tool_invoked": brand.SAIL,
    "tool_returned": brand.SAIL,
    "error_occurred": "#e25a4d",
}


def _term_color(event_type: str) -> str:
    return _TERM_COLOR.get(event_type, "#9bb6c4")


def _short(t: str) -> str:
    return t.replace("model_turn_", "turn.").replace("agent_", "").replace("_", " ")


def _event_label(e: dict[str, Any]) -> str:
    if e.get("tool"):
        return e["tool"]
    if e.get("error_code"):
        return e["error_code"]
    if e.get("stop_reason"):
        return e["stop_reason"]
    if e["type"] == "model_turn_ended" and e.get("tokens_in") is not None:
        return f"in={e['tokens_in']} out={e.get('tokens_out', 0)}"
    return ""


def render_terminal(run: dict[str, Any]):
    """A terminal-native voyage view: header, stats, and a colored event timeline.

    Returns a rich renderable (no browser). Mirrors the constellation's color
    language so the terminal and the HTML read the same.
    """
    from rich.console import Group
    from rich.text import Text

    lines: list[Any] = []

    header = Text()
    header.append("$ ", style=brand.SAIL)
    header.append(f"avp show {run['run_id']}", style=brand.MAST)
    lines.append(header)

    def _fmt(v: Any) -> str:
        return "—" if v is None else str(v)

    stats = Text()
    pairs = [
        ("stop", _fmt(run.get("stop_reason"))),
        ("score", "—" if run.get("score") is None else f"{run['score']:.3f}"),
        ("passed", _fmt(run.get("passed"))),
        ("turns", _fmt(run.get("total_turns"))),
        ("tokens", _fmt(run.get("total_tokens"))),
        ("cost", "—" if run.get("total_cost_usd") is None else f"${run['total_cost_usd']:.4f}"),
        ("events", str(len(run.get("events") or []))),
    ]
    for i, (k, v) in enumerate(pairs):
        if i:
            stats.append("  ·  ", style="#2c4456")
        stats.append(f"{k}=", style="#5a8294")
        stats.append(v, style=brand.MAST)
    lines.append(stats)
    lines.append(Text())

    events = run.get("events") or []
    for i, e in enumerate(events):
        color = _term_color(e["type"])
        row = Text()
        row.append("  ● ", style=color)
        row.append(f"{_short(e['type']):<14}", style=color)
        label = _event_label(e)
        if label:
            row.append(f"  {label}", style="#9fb4c2")
        lines.append(row)
        if i < len(events) - 1:
            lines.append(Text("  │", style="#2c4456"))

    return Group(*lines)


# The vanilla-JS port of TrajectoryConstellation.tsx + brand styling.
_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>avp · trajectory</title>
<style>
  :root { --sail:#f3d28a; --mast:#e6eef3; --sky:#9fd6e7; --bg:#0a131c; }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: radial-gradient(120% 100% at 50% 0%, #11202e 0%, var(--bg) 70%);
    color: #cfe0ea; font: 14px/1.5 'JetBrains Mono','SF Mono',Menlo,Consolas,monospace;
    min-height: 100vh; padding: 28px;
  }
  .wrap { max-width: 1180px; margin: 0 auto; }
  .head { display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px; }
  .cmd { color: var(--mast); }
  .cmd .p { color: var(--sail); margin-right: 6px; }
  button {
    background: transparent; color: #cfe0ea; border: 1px solid #2c4456;
    border-radius: 6px; padding: 4px 10px; cursor: pointer; font: inherit;
  }
  button:hover { border-color: var(--sail); color: var(--sail); }
  .stats { color: #7fa0b3; margin: 10px 0; font-size: 13px; }
  .stats .k { color: #5a8294; } .stats .v { color: #cfe0ea; }
  .stats .sep { color: #2c4456; margin: 0 8px; }
  svg { width: 100%; height: auto; display:block; }
  .detail {
    margin-top: 14px; background: #0d1a26; border: 1px solid #1d3243; border-radius: 8px;
    padding: 12px; white-space: pre-wrap; color: #9fd6e7; font-size: 12px; min-height: 2em;
  }
  .node-label { fill: rgba(230,238,243,0.92); font-size: 10px; pointer-events: none; }
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div class="cmd"><span class="p">$</span><span id="cmd"></span></div>
    <button id="replay">↻ replay</button>
  </div>
  <div class="stats" id="stats"></div>
  <svg id="sky" viewBox="0 0 1180 280" preserveAspectRatio="xMidYMid meet"></svg>
  <pre class="detail" id="detail"></pre>
</div>
<script>
const RUN = __RUN_JSON__;
const W=1180, H=280, PAD_X=48, PAD_Y_TOP=70, PAD_Y_BOT=70;
const SVGNS="http://www.w3.org/2000/svg";

function laneOffset(t){
  if(t==="agent_started"||t==="agent_stopped") return 0;
  if(t==="model_turn_started"||t==="model_turn_ended") return -38;
  if(t==="reasoning_emitted"||t==="text_emitted") return -60;
  if(t==="tool_invoked"||t==="tool_returned") return 50;
  if(t==="error_occurred") return 70;
  if(t==="cost_recorded") return 30;
  if(t==="managed_ref_resolved"||t==="skill_loaded"||t==="mcp_server_connected") return -20;
  return 0;
}
function colorFor(e){
  const t=e.type;
  if(t==="error_occurred") return "#e25a4d";
  if(t.startsWith("model_turn")) return "#e6eef3";
  if(t==="tool_invoked"||t==="tool_returned") return "#f3d28a";
  if(t==="reasoning_emitted") return "#a8d2e2";
  if(t==="text_emitted") return "#9fd6e7";
  if(t==="cost_recorded") return "#5a8294";
  if(t==="agent_started"||t==="agent_stopped") return "#b9e6f5";
  return "#9bb6c4";
}
function radiusFor(e){
  const t=e.type;
  if(t==="agent_started"||t==="agent_stopped") return 7;
  if(t==="model_turn_ended") return 5.5;
  if(t==="tool_invoked"||t==="tool_returned") return 4.5;
  if(t==="error_occurred") return 4;
  return 3;
}
function shortType(t){ return t.replace("model_turn_","turn.").replace("agent_","").replace("_"," "); }
function nodeLabel(e){ return e.tool||e.error_code||e.managed_kind||e.stop_reason||shortType(e.type); }

const events = RUN.events||[];
const n = events.length;
const innerW = W-PAD_X*2, usableH = H-PAD_Y_TOP-PAD_Y_BOT, midY = PAD_Y_TOP+usableH/2;
const positions = events.map((e,i)=>{
  const x = PAD_X + (i*innerW)/Math.max(1,n-1);
  const y = midY + Math.sin(i*0.55)*18 + laneOffset(e.type);
  return {x,y};
});

document.getElementById("cmd").textContent = "avp show --run " + RUN.run_id;
const fmt=(v)=> v==null?"—":v;
document.getElementById("stats").innerHTML = [
  ["stop", fmt(RUN.stop_reason)],
  ["score", RUN.score==null?"—":RUN.score.toFixed(3)],
  ["passed", RUN.passed==null?"—":String(RUN.passed)],
  ["turns", fmt(RUN.total_turns)],
  ["tokens", RUN.total_tokens==null?"—":RUN.total_tokens.toLocaleString()],
  ["cost", RUN.total_cost_usd==null?"—":"$"+RUN.total_cost_usd.toFixed(4)],
  ["events", n],
].map(([k,v])=>`<span class="k">${k}</span>=<span class="v">${v}</span>`).join('<span class="sep">·</span>');

const svg=document.getElementById("sky");
const detail=document.getElementById("detail");
function el(name,attrs){ const e=document.createElementNS(SVGNS,name); for(const k in attrs) e.setAttribute(k,attrs[k]); return e; }

function draw(revealed){
  svg.innerHTML="";
  for(let i=0;i<40;i++){
    const x=((i*137)%W)+0.5, y=((i*71)%H)+0.5, r=(i%3===0)?0.9:0.55;
    svg.appendChild(el("circle",{cx:x,cy:y,r,fill:"rgba(220,235,255,0.18)"}));
  }
  if(positions.length>1){
    const full=positions.map((p,i)=>`${i===0?"M":"L"} ${p.x} ${p.y}`).join(" ");
    svg.appendChild(el("path",{d:full,fill:"none",stroke:"rgba(243,210,138,0.18)","stroke-width":1.5}));
    const lit=positions.slice(0,Math.max(1,revealed)).map((p,i)=>`${i===0?"M":"L"} ${p.x} ${p.y}`).join(" ");
    const litPath=el("path",{d:lit,fill:"none",stroke:"rgba(243,210,138,0.65)","stroke-width":1.75});
    litPath.style.filter="drop-shadow(0 0 4px rgba(243,210,138,0.5))";
    svg.appendChild(litPath);
  }
  for(let i=0;i<revealed;i++){
    const e=events[i], p=positions[i], r=radiusFor(e), c=colorFor(e);
    const g=el("g",{transform:`translate(${p.x} ${p.y})`}); g.style.cursor="pointer";
    g.appendChild(el("circle",{r,fill:c,stroke:c,"stroke-opacity":0.4,"stroke-width":3}));
    g.addEventListener("mouseenter",()=>{
      detail.textContent=JSON.stringify(e,null,2);
      const lbl=el("text",{x:0,y:-r-8,"text-anchor":"middle"}); lbl.setAttribute("class","node-label");
      lbl.textContent=nodeLabel(e); g.appendChild(lbl);
      g.appendChild(el("circle",{r:r+5,fill:"none",stroke:c,"stroke-opacity":0.45,"stroke-width":1}));
    });
    g.addEventListener("mouseleave",()=>{ const t=g.querySelector("text"); if(t)t.remove(); const rings=g.querySelectorAll("circle"); if(rings.length>1)rings[rings.length-1].remove(); });
    svg.appendChild(g);
  }
}

function play(){
  let revealed=0; draw(0);
  if(!n) return;
  const stepMs=Math.max(40,Math.min(180,2400/n));
  const id=setInterval(()=>{ revealed++; draw(revealed); if(revealed>=n){ clearInterval(id); if(events[n-1]) detail.textContent=JSON.stringify(events[n-1],null,2); } },stepMs);
}
document.getElementById("replay").addEventListener("click",play);
play();
</script>
</body>
</html>
"""
