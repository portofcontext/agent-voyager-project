"""Build ATIF content and aggregate metrics for the Recorder."""

import base64
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "ATIF-v1.8"
_IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}


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

    def step(self, timestamp: str, source: str, message: Any) -> dict[str, Any]:
        steps = self.data["steps"]
        step = {
            "step_id": len(steps) + 1,
            "timestamp": timestamp,
            "source": source,
            "message": message,
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
