"""Builds a run's Trajectory (`spec/v0.1/trajectory.md`) from the ATIF objects
an adapter reports, and writes it once when the run ends."""

import base64
import hashlib
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, JsonValue, NonNegativeInt, ValidationError

from avp._base import AVP_VERSION, TrajectorySink
from avp.commission import Commission
from avp.descriptor import AgentDescriptor
from avp.trajectory import (
    Agent,
    Citation,
    ErrorCode,
    FinalMetrics,
    Metrics,
    Recording,
    StopReason,
    Trajectory,
)
from avp.utils.preflight import check_commission
from avp.utils.pricing import Prices, compute_cost, load_prices

SCHEMA_VERSION = "ATIF-v1.8"
ABANDONED_TEXT = "The run ended while the subagent was still running."
UNRETURNED_TEXT = "The run ended before the tool returned."
STOPPED_BEFORE_START_TEXT = "The run stopped before it started."
_REASONING_SEPARATOR = "\n\n"
_IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}
_SKILL_FILE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.?(?:/|$))(?!.*//)(?!.*/$)[^\\:\x00-\x1f]+\Z")


# What an adapter reports


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Text(_Input):
    """Text from the model or a tool."""

    type: Literal["text"] = "text"
    text: str
    citations: list[Citation] | None = None
    """Sources the model cited in the text."""


class Image(_Input):
    """An image saved beside the Trajectory. Made by `Recorder.image`."""

    type: Literal["image"] = "image"
    path: str
    media_type: Literal["image/png", "image/jpeg", "image/gif", "image/webp"]


class Reasoning(_Input):
    """A block of the model's reasoning: readable `text`, or `encrypted_content`
    when the service returned it encrypted."""

    type: Literal["reasoning"] = "reasoning"
    text: str = ""
    signature: str | None = None
    """The service's token for passing the reasoning back to it."""
    encrypted_content: str | None = None


class Call(_Input):
    """A tool call. `server_side` when the model service runs the tool and
    returns its result in the same response, as a `ServerResult`."""

    type: Literal["call"] = "call"
    id: str
    name: str
    arguments: dict[str, Any]
    server_side: bool = False


class ServerResult(_Input):
    """The result of a server-side `Call`, from the same response."""

    type: Literal["server_result"] = "server_result"
    call_id: str
    content: str | list[Text | Image]
    is_error: bool = False
    structured_content: JsonValue = None


Part = Annotated[Text | Image | Reasoning | Call | ServerResult, Field(discriminator="type")]
"""One part of a model response, in the order the service returned it."""


class Usage(_Input):
    """One model response's usage. `prompt_tokens` includes cached and
    cache-creation tokens; `completion_tokens` includes reasoning tokens.
    Without `cost_usd`, the Recorder prices the response."""

    prompt_tokens: NonNegativeInt
    completion_tokens: NonNegativeInt
    cached_tokens: NonNegativeInt | None = None
    cache_creation_input_tokens: NonNegativeInt | None = None
    reasoning_output_tokens: NonNegativeInt | None = None
    cost_usd: float | None = None


class RecorderError(Exception):
    """A report the Recorder can't place: an unknown or repeated ID, or a report
    the run's state doesn't allow. The Recorder records nothing for it."""


def _json(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json", by_alias=True, exclude_none=True)


def _avp(value: dict[str, Any]) -> dict[str, Any]:
    return value.setdefault("extra", {}).setdefault("avp", {})


def _ms(start: datetime, end: datetime) -> int:
    return max(0, round((end - start).total_seconds() * 1000))


def _refusal(error: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(map(str, e['loc'])) or 'Commission'}: {e['msg']}" for e in error.errors()
    )
    return f"the Commission doesn't match the spec: {problems}"


@dataclass
class _Document:
    """One trajectory: the root, or a subagent's."""

    data: dict[str, Any]
    provider: str | None = None
    last: datetime | None = None
    """When the latest step or result was recorded, for default durations."""
    children: list["_Document"] = field(default_factory=list)
    reported: dict[str, Any] | None = None
    """Totals the runtime reported for a subagent whose responses it hides."""
    stop_reason: StopReason | None = None

    def step(self, timestamp: datetime, source: str, message: Any) -> dict[str, Any]:
        steps = self.data["steps"]
        step = {
            "step_id": len(steps) + 1,
            "timestamp": timestamp.isoformat(),
            "source": source,
            "message": message,
        }
        steps.append(step)
        return step

    def stopped(self, reason: StopReason, timestamp: datetime) -> None:
        self.stop_reason = reason
        _avp(self.data).update(stop_reason=reason, stopped_at=timestamp.isoformat())

    def final(self) -> dict[str, Any]:
        """Write `final_metrics` for this trajectory and its subagents, each
        counted once, and return it."""
        children = [child.final() for child in self.children]
        own = [s.get("metrics", {}) for s in self.data["steps"] if s["source"] == "agent"]
        totals: dict[str, Any] = {"total_steps": len(self.data["steps"])}
        if self.reported is not None and not own:
            totals.update({k: v for k, v in self.reported.items() if k != "total_steps"})
            self.data["final_metrics"] = totals
            return totals
        counted = [c for c in children if _get(c, "total_responses", True) != 0]
        responses = len(own) + sum(_get(c, "total_responses", True) or 0 for c in counted)
        avp: dict[str, Any] = {}
        for key, total, in_extra in _TOTALS:
            values = [_get(m, key, in_extra) for m in own]
            values += [_get(c, total, in_extra) for c in counted]
            if values and all(v is not None for v in values):
                (avp if in_extra else totals)[total] = sum(values)
        costs = [m.get("cost_usd") for m in own] + [c.get("total_cost_usd") for c in counted]
        known = [c for c in costs if c is not None]
        if known:
            totals["total_cost_usd"] = sum(known)
            if len(known) < len(costs) or any(
                _get(c, "cost_complete", True) is False for c in counted
            ):
                avp["cost_complete"] = False
        avp["total_responses"] = responses
        totals["extra"] = {"avp": avp}
        self.data["final_metrics"] = totals
        return totals


_TOTALS = (
    ("prompt_tokens", "total_prompt_tokens", False),
    ("completion_tokens", "total_completion_tokens", False),
    ("cached_tokens", "total_cached_tokens", False),
    ("cache_creation_input_tokens", "total_cache_creation_input_tokens", True),
    ("reasoning_output_tokens", "total_reasoning_output_tokens", True),
)
"""Each response metric, its total in `final_metrics`, and whether both are in `extra.avp`."""


def _get(value: dict[str, Any], key: str, in_extra: bool) -> Any:
    return (value.get("extra", {}).get("avp", {}) if in_extra else value).get(key)


def _tool_call(call: Call) -> dict[str, Any]:
    data: dict[str, Any] = {
        "tool_call_id": call.id,
        "function_name": call.name,
        "arguments": call.arguments,
    }
    if call.server_side:
        data["extra"] = {"avp": {"server_side": True}}
    return data


def _reasoning(blocks: list[Reasoning]) -> tuple[str | None, list[dict[str, Any]]]:
    """`reasoning_content` and `reasoning_metadata`. Offsets are left out when
    one readable block is all of `reasoning_content`."""
    readable = [b for b in blocks if b.text]
    texts, metadata, start = [], [], 0
    for block in blocks:
        entry: dict[str, Any] = {}
        if block.text:
            if len(readable) > 1:
                entry.update(start=start, end=start + len(block.text))
            start += len(block.text) + len(_REASONING_SEPARATOR)
            texts.append(block.text)
        if block.signature is not None:
            entry["signature"] = block.signature
        if block.encrypted_content is not None:
            entry["encrypted_content"] = block.encrypted_content
        metadata.append(entry)
    if not any(metadata):
        metadata = []
    return (_REASONING_SEPARATOR.join(texts) if texts else None), metadata


def _metrics(usage: Usage) -> dict[str, Any]:
    data = usage.model_dump(
        exclude_none=True, exclude={"cache_creation_input_tokens", "reasoning_output_tokens"}
    )
    avp = usage.model_dump(
        exclude_none=True, include={"cache_creation_input_tokens", "reasoning_output_tokens"}
    )
    if avp:
        data["extra"] = {"avp": avp}
    return data


@dataclass
class _Call:
    document: _Document
    step: dict[str, Any]
    time: datetime
    returned: bool = False


class Recorder:
    """Builds one run's ATIF document and writes it to `sink` when the run ends."""

    def __init__(
        self,
        sink: TrajectorySink,
        *,
        run_id: str | None = None,
        prices: Prices | None = None,
        now: Callable[[], datetime] | None = None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self._sink = sink
        self._prices = prices
        self._now = now or (lambda: datetime.now(UTC))
        self.run_id = run_id or (new_id or (lambda: str(uuid.uuid4())))()
        self._begun = False
        self._started = False
        self.ended = False
        self._root = self._document(self.run_id, "unknown", "unknown")
        self._subagents: dict[str, _Document] = {}
        self._calls: dict[str, _Call] = {}
        self._assets: dict[str, bytes] = {}
        self._commission: Commission | None = None

    def _document(self, trajectory_id: str, name: str, version: str) -> _Document:
        return _Document(
            {
                "schema_version": SCHEMA_VERSION,
                "session_id": self.run_id,
                "trajectory_id": trajectory_id,
                "agent": {"name": name, "version": version},
                "steps": [],
                "extra": {"avp": {"avp_version": AVP_VERSION}},
            }
        )

    def _check(self, report: str, *, started: bool = True) -> None:
        if self.ended:
            raise RecorderError(f"{report}: the run has ended")
        if started and not self._started:
            raise RecorderError(f"{report}: called before start")

    def _scope(self, subagent: str | None) -> _Document:
        if subagent is None:
            return self._root
        document = self._subagents.get(subagent)
        if document is None:
            raise RecorderError(f"unknown subagent {subagent!r}")
        if document.stop_reason is not None:
            raise RecorderError(f"subagent {subagent!r} has stopped")
        return document

    async def _write(self) -> None:
        self._root.final()
        trajectory = Trajectory.model_validate(self._root.data)
        await self._sink(Recording(trajectory, self._assets.copy()))

    # The run

    async def begin(self, received: JsonValue, descriptor: AgentDescriptor) -> Commission | None:
        """Check the Commission and return it. `received` is None for a run
        without one. When the agent refuses it, the Trajectory is written and
        `ended` is true."""
        self._check("begin", started=False)
        if self._begun:
            raise RecorderError("begin: called twice")
        self._begun = True
        if isinstance(received, dict) and isinstance(received.get("run_id"), str):
            self.run_id = str(received["run_id"])
        self._root = self._document(self.run_id, descriptor.agent_name, descriptor.agent_version)
        _avp(self._root.data["agent"])["descriptor"] = _json(descriptor)
        if received is None:
            return None
        _avp(self._root.data)["commission"] = received
        try:
            commission = Commission.model_validate(received)
        except ValidationError as error:
            await self.error("invalid_commission", _refusal(error))
            return None
        refusal = check_commission(commission, descriptor)
        if refusal is not None:
            await self.error("invalid_commission", refusal)
            return None
        self._commission = commission
        return commission

    async def start(self, agent: Agent, prompt: str, *, system_prompt: str | None = None) -> None:
        """Record what the run uses and its first steps. `agent` holds the
        model, tool definitions, and `extra.avp`; the Recorder keeps the name,
        version, and Descriptor from `begin`. Skill files are copied beside the
        Trajectory, and each skill's `source` points to the copy."""
        self._check("start", started=False)
        if self._started:
            raise RecorderError("start: called twice")
        given = _json(agent)
        avp = given.get("extra", {}).get("avp", {})
        if "model" not in avp:
            raise RecorderError("start: agent.extra.avp.model is required")
        self._capture_skills(avp)
        root = self._root
        root.data["agent"] = {
            **given,
            "name": root.data["agent"]["name"],
            "version": root.data["agent"]["version"],
            "extra": {
                **given.get("extra", {}),
                "avp": {**avp, **root.data["agent"].get("extra", {}).get("avp", {})},
            },
        }
        root.provider = avp["model"]["provider"]
        self._started = True
        now = self._now()
        root.last = now
        _avp(root.data)["started_at"] = now.isoformat()
        if system_prompt is not None:
            root.step(now, "system", system_prompt)
        root.step(now, "user", prompt)

    def _capture_skills(self, avp: dict[str, Any]) -> None:
        supplied = (
            {s.name: s.files for s in (self._commission.skills or [])} if self._commission else {}
        )
        scopes = [("skills", avp.get("skills", []))] + [
            (f"skills/subagent-{i}", child.get("skills", []))
            for i, child in enumerate(avp.get("subagents", []))
        ]
        for prefix, skills in scopes:
            for index, skill in enumerate(skills):
                files = self._skill_files(
                    skill, supplied.get(skill["name"], {}) if prefix == "skills" else {}
                )
                if not files:
                    skill.pop("source", None)
                    continue
                directory = f"{prefix}/{index}-{re.sub(r'[^A-Za-z0-9._-]', '-', skill['name'])}"
                for path, content in files.items():
                    if _SKILL_FILE.match(path) is None:
                        raise ValueError("skill file paths must be relative, without traversal")
                    self._assets[f"{directory}/{path}"] = content
                skill["source"] = f"file:{directory}"

    @staticmethod
    def _skill_files(skill: dict[str, Any], inline: dict[str, str]) -> dict[str, bytes]:
        source = skill.get("source")
        if source is None:
            return {path: text.encode() for path, text in inline.items()}
        uri = urlsplit(source)
        if uri.scheme != "file" or uri.netloc not in {"", "localhost"}:
            raise ValueError(f"skill source must be a local file URI: {source}")
        root = Path(unquote(uri.path)).resolve(strict=True)
        if not (root / "SKILL.md").is_file():
            raise ValueError(f"skill source has no SKILL.md: {source}")
        files = {}
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"skill capture requires regular files: {path}")
            if path.is_file():
                files[path.relative_to(root).as_posix()] = path.read_bytes()
        return files

    async def error(self, code: ErrorCode, message: str, *, subagent: str | None = None) -> None:
        """Record an error as a system step. Before `start`, the error ends the
        run and the Trajectory is written."""
        self._check("error", started=False)
        now = self._now()
        if not self._started:
            self._root.data["steps"] = []
            _avp(self._root.step(now, "system", message))["error_code"] = code
            self._root.stopped("error", now)
            self.ended = True
            await self._write()
            return
        document = self._scope(subagent)
        _avp(document.step(now, "system", message))["error_code"] = code

    async def stop(self, reason: StopReason, output: JsonValue = None) -> None:
        """End the run and write the Trajectory. `output` is the run's result;
        None means the run returned none. Running tool calls get an error
        result, and running subagents are abandoned."""
        if self.ended:
            return
        if not self._started:
            await self.error("agent_crash", STOPPED_BEFORE_START_TEXT)
            return
        running = [id for id, child in self._subagents.items() if child.stop_reason is None]
        for invocation in reversed(running):
            await self.subagent_stopped(invocation, "abandoned")
        for call_id, call in self._calls.items():
            if not call.returned:
                await self.result(call_id, UNRETURNED_TEXT, is_error=True)
        if running and reason == "converged":
            reason = "abandoned"
        self._root.stopped(reason, self._now())
        last = next(
            (s["message"] for s in reversed(self._root.data["steps"]) if s["source"] == "agent"),
            None,
        )
        if not (isinstance(output, str) and output == last) and (
            output is not None or last is not None
        ):
            _avp(self._root.data)["output"] = output
        self.ended = True
        await self._write()

    # Model responses and tools

    def image(self, data: bytes, media_type: str) -> Image:
        """An image part. The image is written beside the Trajectory."""
        if media_type not in _IMAGE_EXTENSIONS:
            raise ValueError(f"ATIF does not support image media type {media_type!r}")
        name = f"images/{hashlib.sha256(data).hexdigest()}.{_IMAGE_EXTENSIONS[media_type]}"
        self._assets[name] = data
        return Image.model_validate({"path": name, "media_type": media_type})

    def image_base64(self, data: str, media_type: str) -> Image:
        """`image`, for base64 data as model services return it."""
        return self.image(base64.b64decode(data, validate=True), media_type)

    async def step(
        self,
        parts: Sequence[Part],
        *,
        usage: Usage | None = None,
        model_name: str | None = None,
        finish_reasons: list[str] | None = None,
        subagent: str | None = None,
    ) -> None:
        """Record one complete model response as an agent step. `parts` are its
        text, images, reasoning, and tool calls, in order. `model_name` is the
        model that answered, when the service reports it."""
        self._check("step")
        document = self._scope(subagent)
        calls = [p for p in parts if isinstance(p, Call)]
        ids = [c.id for c in calls]
        repeated = next((i for i in ids if i in self._calls or ids.count(i) > 1), None)
        if repeated is not None:
            raise RecorderError(f"step: tool call {repeated!r} was already used")
        server = {c.id for c in calls if c.server_side}
        results = [p for p in parts if isinstance(p, ServerResult)]
        unmatched = next((r for r in results if r.call_id not in server), None)
        if unmatched is not None:
            raise RecorderError(f"step: result for unknown server-side call {unmatched.call_id!r}")
        message, message_metadata = self._content([p for p in parts if isinstance(p, Text | Image)])
        reasoning, reasoning_metadata = _reasoning([p for p in parts if isinstance(p, Reasoning)])
        now = self._now()
        step = document.step(now, "agent", message)
        agent_model = document.data["agent"].get("model_name")
        if model_name is not None and model_name != agent_model:
            step["model_name"] = model_name
        if reasoning is not None:
            step["reasoning_content"] = reasoning
        if calls:
            step["tool_calls"] = [_tool_call(c) for c in calls]
        if results:
            step["observation"] = {"results": [self._result(r) for r in results]}
        step["llm_call_count"] = 1
        avp = _avp(step)
        avp["duration_ms"] = _ms(document.last or now, now)
        if finish_reasons:
            avp["finish_reasons"] = finish_reasons
        if message_metadata:
            avp["message_metadata"] = message_metadata
        if reasoning_metadata:
            avp["reasoning_metadata"] = reasoning_metadata
        if usage is not None:
            step["metrics"] = self._priced(_metrics(usage), document, model_name or agent_model)
        document.last = now
        for call in calls:
            if not call.server_side:
                self._calls[call.id] = _Call(document, step, now)

    def _content(
        self, parts: list[Text | Image]
    ) -> tuple[str | list[dict[str, Any]], list[dict[str, Any]]]:
        """ATIF content for text and image parts, and the metadata of their
        citations. One text part is a string."""
        metadata = [
            {"part_index": i, "citations": [_json(c) for c in p.citations]}
            for i, p in enumerate(parts)
            if isinstance(p, Text) and p.citations
        ]
        if not parts:
            return "", metadata
        if len(parts) == 1 and isinstance(parts[0], Text):
            return parts[0].text, metadata
        content = []
        for part in parts:
            if isinstance(part, Text):
                content.append({"type": "text", "text": part.text})
            else:
                if part.path not in self._assets:
                    raise RecorderError(f"image {part.path!r} was not made by this Recorder")
                content.append(
                    {"type": "image", "source": {"media_type": part.media_type, "path": part.path}}
                )
        return content, metadata

    def _result(self, result: ServerResult) -> dict[str, Any]:
        content, metadata = (
            (result.content, [])
            if isinstance(result.content, str)
            else self._content(list(result.content))
        )
        data: dict[str, Any] = {"source_call_id": result.call_id, "content": content}
        avp = {
            "is_error": result.is_error or None,
            "structured_content": result.structured_content,
            "content_metadata": metadata or None,
        }
        avp = {k: v for k, v in avp.items() if v is not None}
        if avp:
            data["extra"] = {"avp": avp}
        return data

    def _priced(
        self, metrics: dict[str, Any], document: _Document, model: str | None
    ) -> dict[str, Any]:
        avp = metrics.get("extra", {}).get("avp", {})
        cached = metrics.get("cached_tokens", 0) + avp.get("cache_creation_input_tokens", 0)
        if cached > metrics.get("prompt_tokens", cached):
            raise RecorderError("step: cached and cache creation tokens exceed prompt_tokens")
        if "cost_usd" in metrics:
            _avp(metrics).setdefault("cost_source", "reported")
            return metrics
        if document.provider is None or model is None or "prompt_tokens" not in metrics:
            return metrics
        if self._prices is None:
            self._prices = load_prices()
        cost = compute_cost(self._prices, document.provider, model, Metrics.model_validate(metrics))
        if cost is not None:
            metrics["cost_usd"] = cost
            _avp(metrics)["cost_source"] = "computed"
        return metrics

    async def result(
        self,
        call_id: str,
        content: str | list[Text | Image],
        *,
        is_error: bool = False,
        structured_content: JsonValue = None,
    ) -> None:
        """Record a tool call's result on the step that holds the call. A call
        that started a subagent is an error exactly when the subagent didn't
        converge."""
        self._check("result")
        call = self._calls.get(call_id)
        if call is None or call.returned:
            state = "unknown" if call is None else "already returned"
            raise RecorderError(f"result: tool call {call_id!r} is {state}")
        data = self._result(
            ServerResult(
                call_id=call_id,
                content=content,
                is_error=is_error,
                structured_content=structured_content,
            )
        )
        call.returned = True
        now = self._now()
        avp = _avp(data)
        avp["finished_at"] = now.isoformat()
        avp["duration_ms"] = _ms(call.time, now)
        child = self._subagents.get(call_id)
        if child is not None:
            if child.stop_reason is not None:
                avp["is_error"] = child.stop_reason != "converged"
            data["subagent_trajectory_ref"] = [{"trajectory_id": child.data["trajectory_id"]}]
        results = call.step.setdefault("observation", {"results": []})["results"]
        results.append(data)
        call.document.last = now

    # Subagents

    async def subagent_started(
        self, call_id: str, name: str, prompt: str, *, agent: Agent | None = None
    ) -> None:
        """Start a subagent's trajectory for the tool call that started it.
        Report its steps with `subagent=call_id`. `agent` is what the subagent
        uses, as in `start`; its name is `name`. Without it, the subagent uses
        the parent's model."""
        self._check("subagent_started")
        call = self._calls.get(call_id)
        if call is None or call.returned:
            raise RecorderError(f"subagent_started: tool call {call_id!r} is unknown or returned")
        if call_id in self._subagents:
            raise RecorderError(f"subagent_started: {call_id!r} was already used")
        child = self._document(f"{self.run_id}/subagent/{call_id}", name, "unknown")
        if agent is not None:
            given = _json(agent)
        else:
            parent = call.document.data["agent"]
            given = {k: v for k, v in parent.items() if k == "model_name"}
            if model := _get(parent, "model", True):
                given["extra"] = {"avp": {"model": model}}
        child.data["agent"] = {**given, "name": name, "version": "unknown"}
        child.provider = (_get(given, "model", True) or {}).get("provider")
        now = self._now()
        child.last = now
        _avp(child.data)["started_at"] = now.isoformat()
        child.step(now, "user", prompt)
        self._subagents[call_id] = child
        call.document.children.append(child)
        call.document.data.setdefault("subagent_trajectories", []).append(child.data)

    async def subagent_stopped(
        self,
        call_id: str,
        reason: StopReason = "converged",
        *,
        final_metrics: FinalMetrics | None = None,
    ) -> None:
        """End a subagent's trajectory. `final_metrics` holds totals the runtime
        reports when it doesn't show the subagent's responses."""
        self._check("subagent_stopped")
        child = self._subagents.get(call_id)
        if child is None or child.stop_reason is not None:
            state = "unknown" if child is None else "already stopped"
            raise RecorderError(f"subagent_stopped: subagent {call_id!r} is {state}")
        for grandchild_id, grandchild in self._subagents.items():
            if grandchild.stop_reason is None and grandchild in child.children:
                await self.subagent_stopped(grandchild_id, "abandoned")
        child.stopped(reason, self._now())
        if final_metrics is not None:
            child.reported = _json(final_metrics)
