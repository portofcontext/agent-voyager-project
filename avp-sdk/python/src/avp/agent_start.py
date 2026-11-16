"""Resolved start configuration, with references to saved skill directories."""

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from pydantic import Field

from avp._base import ObjectSchema, WireModel
from avp.commission import Commission, McpServerHttp, McpServerStdio, ModelRef
from avp.descriptor import McpServer, Skill, Tool

# Use patterns supported by JSON Schema and Python. (?![\s\S]) matches the
# absolute end, unlike $, which also accepts a position before a final newline.
_FILE_PATH = (
    r"^(?!/)"  # Relative paths only.
    r"(?!.*(?:^|/)\.\.?(?:/|$))"  # No dot or parent segments.
    r"(?!.*//)(?!.*/$)"  # No empty segments.
    r"[^\\:\x00-\x1f]+(?![\s\S])"  # Portable separators and no control characters.
)


class StartedSkill(Skill):
    """Skill metadata and a reference to its saved files."""

    path: str | None = Field(default=None, pattern=re.compile(_FILE_PATH))
    """Skill directory relative to agent-start.json, using / separators.
    Absent or null means no files were captured. The original source, when
    present, identifies the runtime directory and is not a portable reference.
    """


class StartedMcpHttp(McpServerHttp):
    """An HTTP MCP connection and its status at start; secrets remain references."""

    status: Literal["connected", "failed", "needs-auth", "disabled"] | None = None
    """The reported connection status. Absent or null means not reported."""


class StartedMcpStdio(McpServerStdio):
    """A stdio MCP connection and its status at start; secrets remain references."""

    status: Literal["connected", "failed", "needs-auth", "disabled"] | None = None
    """The reported connection status. Absent or null means not reported."""


StartedMcpServer = StartedMcpHttp | StartedMcpStdio | McpServer


class StartedSubagent(WireModel):
    """A selected subagent's exposed configuration. No implicit inheritance."""

    name: str
    """The subagent's name."""
    description: str | None = None
    """What the subagent does."""
    system_prompt: str | None = None
    """The effective system prompt; an empty string is an explicit empty prompt."""
    tools: list[Tool] | None = None
    """Resolved tools. Absent or null means not exposed; [] means none."""
    skills: list[StartedSkill] | None = None
    """Selected skills with paths to their captured directories. Absent or null means not exposed; [] means none."""
    mcp_servers: list[StartedMcpServer] | None = None
    """Resolved MCP servers. Absent or null means not exposed; [] means none."""


class AgentStart(WireModel):
    """The resolved configuration exposed by the runtime at the start of a run."""

    avp_version: Literal["0.1"]
    """The AVP version this document follows."""
    run_id: str = Field(min_length=1)
    """The run's nonempty ID, matching the ATIF session_id."""
    prompt: str
    """The effective user prompt."""
    system_prompt: str | None = None
    """The effective system prompt; an empty string is an explicit empty prompt."""
    model: ModelRef
    """The effective initial model and provider, without credentials."""
    tools: list[Tool] | None = None
    """Full resolved tool definitions using MCP fields.
    Absent or null means not exposed; [] means none.
    """
    mcp_servers: list[StartedMcpServer] | None = None
    """Resolved MCP servers, with connection fields when exposed. Secrets remain references.
    Absent or null means not exposed; [] means none.
    """
    skills: list[StartedSkill] | None = None
    """Selected skills with paths to their captured directories. Absent or null means not exposed; [] means none."""
    subagents: list[StartedSubagent] | None = None
    """Selected subagents and their exposed configuration. Absent or null means not exposed; [] means none."""
    output_schema: ObjectSchema | None = None
    """The requested JSON Schema for structured output, when supplied."""


def capture_start(
    context: dict[str, Any],
    commission: Commission | None,
    run_id: str,
    assets: dict[str, bytes],
) -> AgentStart:
    """Capture only selected skills; do not crawl the workspace."""
    data = deepcopy(context)
    captured: dict[str, bytes] = {}
    supplied = {s.name: s.files for s in commission.skills or []} if commission else {}
    connections = (
        {s.id: s.model_dump(mode="json", exclude_none=True) for s in commission.mcp_servers or []}
        if commission
        else {}
    )

    def capture(items: list[dict[str, Any]], prefix: str, *, supplied_skills: bool = False) -> None:
        for index, skill in enumerate(items):
            # Ordinals keep repeated names and subagent scopes separate.
            name = re.sub(r"[^A-Za-z0-9._-]", "-", skill["name"])
            directory = f"{prefix}/{index}-{name}"
            inline = skill.pop("files", None)
            skill.pop("path", None)
            files: dict[str, bytes] = {}
            if source := skill.get("source"):
                uri = urlsplit(source)
                if uri.scheme != "file" or uri.netloc not in {"", "localhost"}:
                    raise ValueError(f"skill source must be a local file URI: {source}")
                root = Path(unquote(uri.path)).resolve(strict=True)
                if not (root / "SKILL.md").is_file():
                    raise ValueError(f"skill source has no SKILL.md: {source}")
                for path in sorted(root.rglob("*")):
                    if path.is_symlink():
                        raise ValueError(f"skill capture requires regular files: {path}")
                    if path.is_file():
                        files[path.relative_to(root).as_posix()] = path.read_bytes()
            else:
                if inline is None and supplied_skills:
                    inline = supplied.get(skill["name"])
                for path, content in (inline or {}).items():
                    files[path] = content.encode("utf-8")
            for path, content in files.items():
                if re.fullmatch(_FILE_PATH, path) is None:
                    raise ValueError("skill file paths must be relative, without traversal")
                captured[f"{directory}/{path}"] = content
            if files:
                skill["path"] = directory

    def servers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**connections.get(s["id"], {}), **s} for s in items]

    capture(data.get("skills", []), "skills", supplied_skills=True)
    if "mcp_servers" in data:
        data["mcp_servers"] = servers(data["mcp_servers"])
    for index, child in enumerate(data.get("subagents", [])):
        capture(child.get("skills", []), f"skills/subagent-{index}")
        if "mcp_servers" in child:
            child["mcp_servers"] = servers(child["mcp_servers"])
    if commission and commission.output_schema is not None:
        data["output_schema"] = commission.output_schema
    started = AgentStart(avp_version="0.1", run_id=run_id, **data)
    assets.update(captured)
    return started
