"""Resolved start configuration, with skill contents inline."""

import base64
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from pydantic import Field, field_validator

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
# Compile to use Python's regex engine, which supports lookahead.
_BASE64 = re.compile(r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?(?![\s\S])")


class BinaryFile(WireModel):
    """Binary skill-file content encoded with the standard base64 alphabet."""

    base64: str = Field(pattern=_BASE64, json_schema_extra={"contentEncoding": "base64"})
    """Base64 content, padded when necessary, with no whitespace."""


class StartedSkill(Skill):
    """Skill metadata and the file contents exposed at start."""

    files: dict[str, str | BinaryFile] | None = Field(
        default=None, json_schema_extra={"propertyNames": {"pattern": _FILE_PATH}}
    )
    """Paths relative to the skill directory, mapped to UTF-8 text or base64.
    Absent or null means contents were not exposed. An empty map means no files.
    """

    @field_validator("files")
    @classmethod
    def _relative_paths(cls, files: dict[str, str | BinaryFile] | None):
        for path in files or {}:
            if re.fullmatch(_FILE_PATH, path) is None:
                raise ValueError("skill file paths must be relative, without traversal")
        return files


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
    """Selected skills with exposed file contents. Absent or null means not exposed; [] means none."""
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
    """Selected skills with exposed file contents. Absent or null means not exposed; [] means none."""
    subagents: list[StartedSubagent] | None = None
    """Selected subagents and their exposed configuration. Absent or null means not exposed; [] means none."""
    output_schema: ObjectSchema | None = None
    """The requested JSON Schema for structured output, when supplied."""


def capture_start(
    context: dict[str, Any], commission: Commission | None, run_id: str
) -> AgentStart:
    """Capture only selected skills; do not crawl the workspace."""
    data = deepcopy(context)
    supplied = {s.name: s.files for s in commission.skills or []} if commission else {}
    connections = (
        {s.id: s.model_dump(mode="json", exclude_none=True) for s in commission.mcp_servers or []}
        if commission
        else {}
    )

    def capture(items: list[dict[str, Any]], *, supplied_skills: bool = False) -> None:
        for skill in items:
            if source := skill.get("source"):
                uri = urlsplit(source)
                if uri.scheme != "file" or uri.netloc not in {"", "localhost"}:
                    raise ValueError(f"skill source must be a local file URI: {source}")
                root = Path(unquote(uri.path)).resolve(strict=True)
                if not (root / "SKILL.md").is_file():
                    raise ValueError(f"skill source has no SKILL.md: {source}")
                files: dict[str, Any] = {}
                for path in sorted(root.rglob("*")):
                    if path.is_symlink():
                        raise ValueError(f"skill capture requires regular files: {path}")
                    if path.is_file():
                        content = path.read_bytes()
                        try:
                            value: Any = content.decode("utf-8")
                        except UnicodeDecodeError:
                            value = {"base64": base64.b64encode(content).decode("ascii")}
                        files[path.relative_to(root).as_posix()] = value
                skill["files"] = files
            elif "files" not in skill and supplied_skills and skill["name"] in supplied:
                skill["files"] = deepcopy(supplied[skill["name"]])

    def servers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**connections.get(s["id"], {}), **s} for s in items]

    capture(data.get("skills", []), supplied_skills=True)
    if "mcp_servers" in data:
        data["mcp_servers"] = servers(data["mcp_servers"])
    for child in data.get("subagents", []):
        capture(child.get("skills", []))
        if "mcp_servers" in child:
            child["mcp_servers"] = servers(child["mcp_servers"])
    if commission and commission.output_schema is not None:
        data["output_schema"] = commission.output_schema
    return AgentStart(avp_version="0.1", run_id=run_id, **data)
