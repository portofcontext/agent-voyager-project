#!/usr/bin/env python3
"""One-shot migrator: rewrite v0.1 conformance case files from the pre-CloudEvents
shape into the post-refactor shape (CloudEvents envelopes + OTel attribute names
nested under `data`).

Run from repo root once during the v0.1 refactor:

    uv run python scripts/migrate-conformance-cases.py

Idempotent: cases already in the new shape (`type` starting with `aep.`) are skipped.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "conformance" / "v0.1" / "cases"

# Field mapping (old flat name → new dotted/nested location relative to `data`)
FLAT_TO_DATA: dict[str, str] = {
    # text / cost
    "text": "aep.text",
    "cost_usd": "aep.cost_usd",
    # tokens
    "tokens_input": "gen_ai.usage.input_tokens",
    "tokens_output": "gen_ai.usage.output_tokens",
    "tokens_cache_read": "gen_ai.usage.cache_read.input_tokens",
    "tokens_cache_write": "gen_ai.usage.cache_creation.input_tokens",
    # tool
    "tool": "gen_ai.tool.name",
    "call_id": "gen_ai.tool.call.id",
    "input": "gen_ai.tool.call.arguments",
    "output": "aep.tool.result.text",
    "output_json": "aep.tool.result.structured",
    "rejected": "aep.tool.rejected",
    "rejection_reason": "aep.tool.rejection_reason",
    # tool_exec
    "request_id": "aep.request_id",
    "timeout_ms": "aep.timeout_ms",
    # agent_stopped
    "reason": "aep.reason",
    "state": "aep.state",
    "total_tokens": "aep.total_tokens",
    "total_cost_usd": "aep.total_cost_usd",
    "total_turns": "aep.total_turns",
    "duration_ms": "duration_ms",  # stays plain on data
    # verifier
    "name": "aep.verifier.name",  # only when type=verifier_evaluated; we override per-type below
    "passed": "aep.verifier.passed",
    # error_occurred / generic message+code
    "code": "aep.error.code",
    "message": "aep.error.message",
    # agent_started
    "model": "gen_ai.request.model",
    "tools": "tools",
    "skills": "skills",
    "prompt": "prompt",
    "system_prompt": "system_prompt",
    "thread_id": "aep.thread_id",
    "tags": "aep.tags",
    "meta": "aep.meta",
    # text/skill
    "skill_source": "aep.skill.source",
    # context
    "context_messages": "aep.context_messages",
}

# Per-event-type overrides (when the same flat name maps differently)
PER_TYPE_OVERRIDES: dict[str, dict[str, str]] = {
    "tool_failed": {"error": "aep.tool.error"},
    "verifier_evaluated": {
        "name": "aep.verifier.name",
        "data": "aep.verifier.data",
        "error": "aep.verifier.error",
    },
    "skill_loaded": {"name": "aep.skill.name"},
    "skill_executed": {"name": "aep.skill.name"},
    "error_occurred": {"code": "aep.error.code", "message": "aep.error.message"},
}

# Fields that stay at envelope level (CloudEvents envelope, not `data`)
ENVELOPE_FIELDS = {
    "specversion",
    "id",
    "source",
    "type",
    "subject",
    "time",
    "datacontenttype",
    "dataschema",
    "aep.correlation_id",
}

# Fields that stay plain on `data` without renaming
DATA_PLAIN_FIELDS = {"step", "duration_ms"}


def _short(t: str) -> str:
    """Strip the `aep.` prefix to get the legacy short type name."""
    return t[len("aep.") :] if t.startswith("aep.") else t


def _migrate_match(m: dict[str, Any]) -> dict[str, Any]:
    """Migrate one matcher dict (`{type, run_id, ...}`) to envelope+data shape."""
    if not isinstance(m, dict):
        return m

    out: dict[str, Any] = {}
    type_val = m.get("type")
    if isinstance(type_val, str):
        new_type = type_val if type_val.startswith("aep.") else f"aep.{type_val}"
        out["type"] = new_type
    short_type = _short(out.get("type", "")) if "type" in out else ""

    overrides = PER_TYPE_OVERRIDES.get(short_type, {})

    data: dict[str, Any] = {}
    for k, v in m.items():
        if k == "type":
            continue
        if k == "source":
            # source moved to envelope. legacy values were "runner"/"supervisor";
            # remap to URI form.
            if v == "runner":
                out["source"] = "aep://runner"
            elif v == "supervisor":
                out["source"] = "aep://supervisor"
            else:
                out["source"] = v
            continue
        if k == "run_id":
            out["subject"] = v
            continue
        if k == "ts":
            out["time"] = v
            continue
        if k == "correlation_id":
            out["aep.correlation_id"] = v
            continue
        if k == "extensions":
            # The extensions envelope was dropped in the refactor. Migrate any
            # contents into `data` (caller's loss; the concept is gone).
            if isinstance(v, dict):
                data.update(v)
            continue
        # Per-type override first, then global flat→data map.
        target = overrides.get(k) or FLAT_TO_DATA.get(k)
        if target is None and k in DATA_PLAIN_FIELDS:
            target = k
        if target is None:
            # Unknown legacy field: pass through untouched at data level.
            data[k] = v
            continue
        # Recurse for nested matchers (e.g. `state` is itself a dict).
        data[target] = v

    if data:
        out["data"] = data
    return out


def _migrate_send_payload(send: Any, scripted_request_id_paths: bool = True) -> Any:
    """Migrate a scripted_supervisor `send` payload (a tool_exec_resolved event).

    Replaces old-shape resolved events with CloudEvents envelopes containing
    JSON-RPC response payloads.
    """
    if not isinstance(send, dict):
        return send

    type_val = send.get("type")
    if type_val == "tool_exec_resolved" or type_val == "aep.tool_exec_resolved":
        # Build the new envelope
        request_id = send.get("request_id", "{{event.data.aep.request_id}}")
        # Determine result vs error
        rpc: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
        }
        if "error" in send and send["error"] is not None:
            err_msg = send["error"]
            rpc["error"] = {"code": -32000, "message": err_msg}
        else:
            output = send.get("output", "")
            output_json = send.get("output_json")
            rpc["result"] = output_json if output_json is not None else output

        data: dict[str, Any] = {
            # Placeholder span context — runner restamps on receipt.
            "trace_id": "0" * 32,
            "span_id": "0" * 16,
            "parent_span_id": "0" * 16,
            "aep.request_id": request_id,
            "rpc": rpc,
        }
        envelope: dict[str, Any] = {
            "specversion": "1.0",
            "id": str(uuid.uuid4()),
            "source": "aep://supervisor",
            "type": "aep.tool_exec_resolved",
            "subject": send.get("run_id", "{{run_id}}"),
            "time": send.get("ts", "{{now}}"),
            "datacontenttype": "application/json",
            "data": data,
        }
        if "correlation_id" in send:
            envelope["aep.correlation_id"] = send["correlation_id"]
        if "extensions" in send and isinstance(send["extensions"], dict):
            # Drop or fold — preserve under data extensions for now.
            for k, v in send["extensions"].items():
                envelope["data"][k] = v
        return envelope
    return send


def _rewrite_placeholders(node: Any) -> Any:
    """Update {{event.foo}} placeholders that still reference legacy paths."""
    if isinstance(node, str):
        s = node
        # event.run_id -> event.subject
        s = re.sub(r"\{\{\s*event\.run_id\s*\}\}", "{{event.subject}}", s)
        # event.request_id -> event.data.aep.request_id (for tool_exec_request matches)
        s = re.sub(r"\{\{\s*event\.request_id\s*\}\}", "{{event.data.aep.request_id}}", s)
        # event.call_id -> event.data.gen_ai.tool.call.id
        s = re.sub(r"\{\{\s*event\.call_id\s*\}\}", "{{event.data.gen_ai.tool.call.id}}", s)
        # event.tool -> event.data.gen_ai.tool.name
        s = re.sub(r"\{\{\s*event\.tool\s*\}\}", "{{event.data.gen_ai.tool.name}}", s)
        return s
    if isinstance(node, dict):
        return {k: _rewrite_placeholders(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_rewrite_placeholders(v) for v in node]
    return node


def _migrate_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Update Config — currently only the tool descriptors need camelCase."""
    if "tools" in cfg and isinstance(cfg["tools"], list):
        for t in cfg["tools"]:
            if isinstance(t, dict) and "input_schema" in t and "inputSchema" not in t:
                t["inputSchema"] = t.pop("input_schema")
            # Old `timeout_ms` lives in `_meta.aep.timeout_ms` per MCP convention.
            if isinstance(t, dict) and "timeout_ms" in t:
                meta = t.setdefault("_meta", {})
                meta_aep = meta.setdefault("aep", {})
                if "timeout_ms" not in meta_aep:
                    meta_aep["timeout_ms"] = t.pop("timeout_ms")
                else:
                    t.pop("timeout_ms", None)
    if "skills" in cfg and isinstance(cfg["skills"], list):
        for s in cfg["skills"]:
            if isinstance(s, dict) and "source" in s and "aep.source" not in s:
                s["aep.source"] = s.pop("source")
    return cfg


def migrate_case(doc: dict[str, Any]) -> dict[str, Any]:
    if "config" in doc and isinstance(doc["config"], dict):
        doc["config"] = _migrate_config(doc["config"])

    if "expectations" in doc and isinstance(doc["expectations"], dict):
        exp = doc["expectations"]
        if "events" in exp and isinstance(exp["events"], list):
            exp["events"] = [
                {**m, "match": _migrate_match(m["match"])}
                if isinstance(m, dict) and "match" in m
                else m
                for m in exp["events"]
            ]
        if "forbidden_events" in exp and isinstance(exp["forbidden_events"], list):
            exp["forbidden_events"] = [
                {**m, "match": _migrate_match(m["match"])}
                if isinstance(m, dict) and "match" in m
                else m
                for m in exp["forbidden_events"]
            ]

    if "scripted_supervisor" in doc and isinstance(doc["scripted_supervisor"], list):
        for step in doc["scripted_supervisor"]:
            if not isinstance(step, dict):
                continue
            on = step.get("on")
            if isinstance(on, dict) and "match" in on:
                on["match"] = _migrate_match(on["match"])
            if "send" in step:
                step["send"] = _migrate_send_payload(step["send"])

    # Rewrite placeholders globally (after structural migration)
    doc = _rewrite_placeholders(doc)

    return doc


def already_migrated(doc: dict[str, Any]) -> bool:
    """Heuristic: a migrated case has events whose `type` starts with `aep.`."""
    exp = doc.get("expectations", {})
    events = exp.get("events", [])
    for ev in events:
        if isinstance(ev, dict):
            t = ev.get("match", {}).get("type")
            if isinstance(t, str) and t.startswith("aep."):
                return True
    return False


def main() -> int:
    paths = sorted(CASES.rglob("*.json"))
    migrated = 0
    skipped = 0
    for p in paths:
        doc = json.loads(p.read_text())
        if already_migrated(doc):
            print(f"  skip   {p.relative_to(ROOT)}  (already migrated)")
            skipped += 1
            continue
        new_doc = migrate_case(doc)
        p.write_text(json.dumps(new_doc, indent=2, ensure_ascii=False) + "\n")
        print(f"  rewrite {p.relative_to(ROOT)}")
        migrated += 1
    print(f"\nDone: {migrated} migrated, {skipped} already migrated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
