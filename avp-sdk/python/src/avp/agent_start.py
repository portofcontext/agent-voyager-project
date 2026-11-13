"""Resolved start configuration, with skill contents inline."""

import base64
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from avp._base import ObjectSchema, WireModel
from avp.commission import Commission, McpServerHttp, McpServerStdio, ModelRef
from avp.descriptor import McpServer, Skill, Tool


class BinaryFile(WireModel):
    base64: str


class StartedSkill(Skill):
    files: dict[str, str | BinaryFile] | None = None


class StartedMcpHttp(McpServerHttp):
    status: Literal["connected", "failed", "needs-auth", "disabled"] | None = None


class StartedMcpStdio(McpServerStdio):
    status: Literal["connected", "failed", "needs-auth", "disabled"] | None = None


StartedMcpServer = StartedMcpHttp | StartedMcpStdio | McpServer


class StartedSubagent(WireModel):
    name: str
    description: str | None = None
    system_prompt: str | None = None
    tools: list[Tool] | None = None
    skills: list[StartedSkill] | None = None
    mcp_servers: list[StartedMcpServer] | None = None


class AgentStart(WireModel):
    avp_version: Literal["0.1"]
    run_id: str
    prompt: str
    system_prompt: str | None = None
    model: ModelRef
    tools: list[Tool] | None = None
    mcp_servers: list[StartedMcpServer] | None = None
    skills: list[StartedSkill] | None = None
    subagents: list[StartedSubagent] | None = None
    output_schema: ObjectSchema | None = None


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
