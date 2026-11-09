"""Export AVP events as ATIF-v1.8, without a Harbor runtime dependency.

ATIF is the target record. Extensions preserve operational capabilities that
its standard fields do not cover, not the source event representation.
See ../../../../docs/atif.md for the mapping.
"""

import argparse
import base64
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from avp.trajectory import Event, parse_trajectory_event

SCHEMA_VERSION = "ATIF-v1.8"
_IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}


@dataclass
class AtifExport:
    """One JSON document and its relative image assets, ready to write together."""

    trajectory: dict[str, Any]
    assets: dict[str, bytes] = field(default_factory=dict)

    def write(self, path: Path) -> None:
        """Write the document and its images beneath the document's directory."""
        path.parent.mkdir(parents=True, exist_ok=True)
        for name, data in self.assets.items():
            asset = path.parent / name
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(data)
        path.write_text(
            json.dumps(self.trajectory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def _extra(**values: Any) -> dict[str, Any]:
    return {"avp": values}


def _metadata(value: dict[str, Any]) -> dict[str, Any]:
    return value.setdefault("extra", {}).setdefault("avp", {})


def _remaining(value: dict[str, Any], represented: set[str]) -> dict[str, Any]:
    return {k: v for k, v in value.items() if k not in represented}


def _model_metadata(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": model["provider"],
        **({"base_url": model["base_url"]} if "base_url" in model else {}),
    }


def _content_metadata(content: Any) -> list[dict[str, Any]]:
    """Attach citations, refusals, and provider annotations to visible parts."""
    if not isinstance(content, list):
        return []
    metadata = []
    for i, block in enumerate(content):
        if not isinstance(block, dict):
            return []  # Arbitrary provider output is represented verbatim as JSON text.
        kind = block.get("type")
        if kind == "text" and isinstance(block.get("text"), str):
            details = _remaining(block, {"type", "text"})
        elif kind == "refusal" and isinstance(block.get("refusal"), str):
            details = {**_remaining(block, {"type", "refusal"}), "refusal": True}
        elif (
            kind == "image"
            and isinstance(block.get("source"), dict)
            and block["source"].get("type") == "base64"
        ):
            details = _remaining(block, {"type", "source"})
            source_details = _remaining(block["source"], {"type", "media_type", "data"})
            if source_details:
                details["source"] = source_details
        else:
            return []
        if details:
            metadata.append({"part_index": i, "annotations": details})
    return metadata


def _content(value: Any, assets: dict[str, bytes]) -> str | list[dict[str, Any]]:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    parts: list[dict[str, Any]] = []
    for block in value:
        if not isinstance(block, dict):
            return json.dumps(value, ensure_ascii=False)
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append({"type": "text", "text": block["text"]})
        elif block.get("type") == "refusal" and isinstance(block.get("refusal"), str):
            parts.append({"type": "text", "text": block["refusal"]})
        elif (
            block.get("type") == "image"
            and isinstance(block.get("source"), dict)
            and block["source"].get("type") == "base64"
            and isinstance(block["source"].get("data"), str)
            and isinstance(block["source"].get("media_type"), str)
        ):
            source = block["source"]
            media = source["media_type"]
            if media not in _IMAGE_EXTENSIONS:
                raise ValueError(f"ATIF does not support image media type {media!r}")
            data = base64.b64decode(source["data"], validate=True)
            name = f"images/{hashlib.sha256(data).hexdigest()}.{_IMAGE_EXTENSIONS[media]}"
            assets[name] = data
            parts.append({"type": "image", "source": {"media_type": media, "path": name}})
        else:
            return json.dumps(value, ensure_ascii=False)
    if not parts:
        return ""
    if len(parts) == 1 and parts[0]["type"] == "text":
        return parts[0]["text"]
    return parts


def _metrics(usage: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for source, target in (
        ("input_tokens", "prompt_tokens"),
        ("output_tokens", "completion_tokens"),
        ("cache_read_input_tokens", "cached_tokens"),
    ):
        if source in usage:
            metrics[target] = usage[source]
    if "cost_usd" in usage and usage.get("cost_source") != "unknown":
        metrics["cost_usd"] = usage["cost_usd"]
    remaining = {
        k: v
        for k, v in usage.items()
        if k not in {"input_tokens", "output_tokens", "cache_read_input_tokens", "cost_usd"}
    }
    if remaining:
        metrics["extra"] = _extra(**remaining)
    return metrics


@dataclass
class _Document:
    data: dict[str, Any]
    usages: list[dict[str, Any]] = field(default_factory=list)
    children: list["_Document"] = field(default_factory=list)

    def step(self, event: dict[str, Any], source: str, message: Any) -> dict[str, Any]:
        steps = self.data["steps"]
        step = {
            "step_id": len(steps) + 1,
            "timestamp": event["time"],
            "source": source,
            "message": message,
            **({"extra": _extra(annotations=event["meta"])} if event.get("meta") else {}),
        }
        steps.append(step)
        return step

    def finish(self) -> list[dict[str, Any]]:
        usages = self.usages.copy()
        for child in self.children:
            usages.extend(child.finish())
        totals: dict[str, Any] = {"total_steps": len(self.data["steps"])}
        known: dict[str, Any] = {}
        for source, target in (
            ("input_tokens", "total_prompt_tokens"),
            ("output_tokens", "total_completion_tokens"),
            ("cache_read_input_tokens", "total_cached_tokens"),
            ("cost_usd", "total_cost_usd"),
        ):
            measured = [
                u[source]
                for u in usages
                if source in u and not (source == "cost_usd" and u.get("cost_source") == "unknown")
            ]
            if len(measured) == len(usages):
                totals[target] = sum(measured)
            else:
                known[target] = sum(measured)
        totals["extra"] = _extra(usage_scope="subtree", known_totals=known)
        self.data["final_metrics"] = totals
        return usages


def _document(run_id: str, trajectory_id: str, name: str, version: str) -> _Document:
    return _Document(
        {
            "schema_version": SCHEMA_VERSION,
            "session_id": run_id,
            "trajectory_id": trajectory_id,
            "agent": {"name": name, "version": version},
            "steps": [],
            "extra": _extra(complete=False),
            "notes": "Usage totals include descendants once; total_steps counts this document's "
            "steps only. Missing metrics are unknown. Unrecorded context is not reconstructed.",
        }
    )


def _observation(step: dict[str, Any], call_id: str | None) -> dict[str, Any]:
    results = step.setdefault("observation", {"results": []})["results"]
    for result in results:
        if result.get("source_call_id") == call_id:
            return result
    result = {} if call_id is None else {"source_call_id": call_id}
    results.append(result)
    return result


def to_atif(events: Iterable[Event]) -> AtifExport:
    """Project one AVP run, including incomplete runs, into an ATIF bundle.

    Requires an agent_described event. Rejects mixed runs, duplicate event/call
    IDs, unknown subagent scopes, and unmatched results rather than guessing.
    Call IDs are scoped to each agent invocation. No network or file IO occurs.
    """
    raw = [e.model_dump(mode="json", exclude_none=True) for e in events]
    if not raw:
        raise ValueError("cannot export an empty trajectory")
    run_id = raw[0]["run_id"]
    if any(e["run_id"] != run_id for e in raw):
        raise ValueError("ATIF export requires exactly one run_id")
    if len({e["id"] for e in raw}) != len(raw):
        raise ValueError("duplicate AVP event IDs")
    descriptors = [e["data"]["descriptor"] for e in raw if e["type"] == "agent_described"]
    if len(descriptors) != 1:
        raise ValueError("ATIF export requires exactly one agent_described event")
    descriptor = descriptors[0]
    root = _document(
        run_id, f"{run_id}/root", descriptor["agent_name"], descriptor["agent_version"]
    )
    documents: dict[str | None, _Document] = {None: root}
    calls: dict[tuple[str | None, str], dict[str, Any]] = {}
    delegations: dict[str, dict[str, Any]] = {}
    returned: set[tuple[str | None, str]] = set()
    assets: dict[str, bytes] = {}
    started = False
    for event in raw:
        kind, data = event["type"], event["data"]
        scope = data.get("subagent_invocation_id")
        if scope not in documents:
            raise ValueError(f"unknown subagent scope {scope!r}")
        doc = documents[scope]
        if kind == "run_requested":
            root.data["extra"]["avp"]["requested_at"] = event["time"]
            if event.get("meta"):
                root.data["extra"]["avp"]["annotations"] = event["meta"]
        elif kind == "agent_started":
            started = True
            root.data["extra"]["avp"]["started_at"] = event["time"]
            agent = root.data["agent"]
            agent["model_name"] = data["model"]["id"]
            agent["extra"] = _extra(
                **_model_metadata(data["model"]),
                **{k: data[k] for k in ("mcp_servers", "skills", "subagents") if k in data},
            )
            agent["tool_definitions"] = [
                {
                    "type": "function",
                    **(
                        {"extra": _extra(**_remaining(t, {"name", "description", "inputSchema"}))}
                        if _remaining(t, {"name", "description", "inputSchema"})
                        else {}
                    ),
                    "function": {
                        "name": t["name"],
                        "parameters": t["inputSchema"],
                        **({"description": t["description"]} if "description" in t else {}),
                    },
                }
                for t in data.get("tools", [])
            ]
            if "system_prompt" in data:
                root.step(event, "system", data["system_prompt"])
            root.step(event, "user", data["prompt"])
        elif kind == "assistant_message":
            content = data["content"]
            step = doc.step(
                event,
                "agent",
                _content([b for b in content if b["type"] in ("text", "image", "refusal")], assets),
            )
            step.update(
                model_name=data.get("response_model", data["model"]["id"]),
                llm_call_count=1,
                metrics=_metrics(data["usage"]),
            )
            _metadata(step).update(
                duration_ms=data["duration_ms"],
                **_model_metadata(data["model"]),
                **({"requested_model": data["model"]["id"]} if "response_model" in data else {}),
                **({"finish_reasons": data["finish_reasons"]} if "finish_reasons" in data else {}),
            )
            visible = [b for b in content if b["type"] in ("text", "image", "refusal")]
            content_metadata = _content_metadata(visible)
            if content_metadata:
                _metadata(step)["message_metadata"] = content_metadata
            doc.usages.append(data["usage"])
            reasoning = [
                b["thinking"] for b in content if b["type"] == "thinking" and not b.get("redacted")
            ]
            if reasoning:
                step["reasoning_content"] = "\n".join(reasoning)
            reasoning_metadata = []
            offset = 0
            for block in content:
                if block["type"] == "thinking":
                    details = _remaining(block, {"type", "thinking"})
                    if block.get("redacted"):
                        details["encrypted_content"] = block["thinking"]
                    elif details:
                        details.update(start=offset, end=offset + len(block["thinking"]))
                    if not block.get("redacted"):
                        offset += len(block["thinking"]) + 1
                    if details:
                        reasoning_metadata.append(details)
            if reasoning_metadata:
                _metadata(step)["reasoning_metadata"] = reasoning_metadata
            for block in content:
                if block["type"] in ("tool_use", "server_tool_use"):
                    key = (scope, block["id"])
                    if key in calls:
                        raise ValueError(f"duplicate tool call {key!r}")
                    calls[key] = step
                    step.setdefault("tool_calls", []).append(
                        {
                            "tool_call_id": block["id"],
                            "function_name": block["name"],
                            "arguments": block["input"],
                            "extra": _extra(
                                server_side=block["type"] == "server_tool_use",
                                **(
                                    {
                                        "provider_metadata": _remaining(
                                            block, {"type", "id", "name", "input"}
                                        )
                                    }
                                    if _remaining(block, {"type", "id", "name", "input"})
                                    else {}
                                ),
                            ),
                        }
                    )
            for block in content:
                if block["type"] in ("tool_result", "server_tool_result"):
                    _result(calls, returned, scope, block, event, assets)
        elif kind == "tool_invoked":
            key = (scope, data["tool_call_id"])
            if key not in calls:
                raise ValueError(f"unmatched tool invocation {key!r}")
            call = next(c for c in calls[key]["tool_calls"] if c["tool_call_id"] == key[1])
            _metadata(call).update(started_at=event["time"])
            if "mcp_server_id" in data:
                _metadata(call)["mcp_server_id"] = data["mcp_server_id"]
            if event.get("meta"):
                _metadata(call)["annotations"] = event["meta"]
        elif kind == "tool_returned":
            _result(calls, returned, scope, data["tool_result"], event, assets)
        elif kind == "subagent_invoked":
            invocation = data["invocation_id"]
            if invocation in documents:
                raise ValueError(f"duplicate subagent invocation {invocation!r}")
            child = _document(
                run_id, f"{run_id}/subagent/{invocation}", data["subagent_name"], "unknown"
            )
            documents[invocation] = child
            doc.children.append(child)
            doc.data.setdefault("subagent_trajectories", []).append(child.data)
            child.data["extra"]["avp"]["started_at"] = event["time"]
            _metadata(
                child.step(event, "user", json.dumps(data["subagent_input"], ensure_ascii=False))
            )["input_encoding"] = "json"
            call_step = calls.get((scope, invocation))
            if call_step is None:
                call_step = doc.step(event, "system", f"Delegated to {data['subagent_name']}.")
                result = _observation(call_step, None)
            else:
                result = _observation(call_step, invocation)
            result["subagent_trajectory_ref"] = [{"trajectory_id": child.data["trajectory_id"]}]
            delegations[invocation] = result
        elif kind == "subagent_returned":
            invocation = data["invocation_id"]
            if invocation not in delegations:
                raise ValueError(f"unmatched subagent result {invocation!r}")
            child = documents[invocation]
            child.data["extra"]["avp"].update(
                complete=True,
                stop_reason=data["subagent_reason"],
                stopped_at=event["time"],
                duration_ms=data["duration_ms"],
            )
            if event.get("meta"):
                child.data["extra"]["avp"]["annotations"] = event["meta"]
            result = delegations[invocation]
            # A real tool result, if present, is the model-facing observation.
            result.setdefault("content", data["subagent_result_text"])
            if not child.usages:
                usage = data.get("subagent_usage", {})
                child.usages.append(usage)
                details = _metrics(usage).get("extra", {}).get("avp", {})
                if details:
                    child.data["extra"]["avp"]["usage_details"] = details
        elif kind == "error_occurred":
            _metadata(doc.step(event, "system", data["error_message"]))["error_code"] = data[
                "error_code"
            ]
        elif kind == "agent_stopped":
            root.data["extra"]["avp"].update(stop_reason=data["reason"], stopped_at=event["time"])
            if "output" in data:
                root.data["extra"]["avp"]["output"] = data["output"]
            if event.get("meta"):
                root.data["extra"]["avp"]["annotations"] = event["meta"]
    last = raw[-1]
    root.data["extra"]["avp"]["complete"] = (started and last["type"] == "agent_stopped") or (
        not started and last["type"] == "error_occurred"
    )
    if not started and last["type"] == "error_occurred":
        root.data["extra"]["avp"].update(stop_reason="error", stopped_at=last["time"])
    if not root.data["steps"]:
        root.step(last, "system", "Run ended before any interaction was recorded.")
    root.finish()
    return AtifExport(root.data, assets)


def _result(
    calls: dict,
    returned: set,
    scope: str | None,
    block: dict[str, Any],
    event: dict[str, Any],
    assets: dict[str, bytes],
) -> None:
    key = (scope, block["tool_use_id"])
    if key not in calls:
        raise ValueError(f"unmatched tool result {key!r}")
    if key in returned:
        raise ValueError(f"duplicate tool result {key!r}")
    returned.add(key)
    result = _observation(calls[key], block["tool_use_id"])
    result.update(
        content=_content(block["content"], assets),
        extra=_extra(
            finished_at=event["time"],
            **(
                {"duration_ms": event["data"]["duration_ms"]}
                if event["type"] == "tool_returned"
                else {}
            ),
            **({"annotations": event["meta"]} if event.get("meta") else {}),
            is_error=block.get("is_error", False),
            **(
                {"structured_content": block["structured_content"]}
                if "structured_content" in block
                else {}
            ),
        ),
    )
    provider_metadata = _remaining(
        block, {"type", "tool_use_id", "name", "content", "is_error", "structured_content"}
    )
    if provider_metadata:
        _metadata(result)["provider_metadata"] = provider_metadata
    content_metadata = _content_metadata(block["content"])
    if content_metadata:
        _metadata(result)["content_metadata"] = content_metadata


def main() -> None:
    """Export an NDJSON trajectory: python -m avp.utils.atif INPUT --out OUTPUT."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    events: list[Event] = []
    try:
        for number, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            event = parse_trajectory_event(line)
            if event is None:
                raise ValueError(f"line {number}: unknown event type")
            events.append(event)
        to_atif(events).write(args.out)
    except (ValueError, OSError) as error:
        parser.exit(1, f"ATIF export failed: {error}\n")


if __name__ == "__main__":
    main()
