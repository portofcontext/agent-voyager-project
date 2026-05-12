"""Environment discovery for Commission authoring.

A Commission author writing `enabled_builtin_tools` (the SDK preset
allowlist) needs visibility into what's actually available before
authoring the Commission. Some surfaces are knowable programmatically
(SDK constants we ship); others — like filesystem-discovered skills
under `~/.claude/skills/` and custom subagents under `.claude/agents/`
— require walking the runtime environment.

This module exposes `discover_environment()` which combines both.
Filesystem-discovered skills/subagents inform the supervisor's
deployment-layer decisions about what to mount into the agent's
workspace; the v0.1 wire doesn't surface them as managed assets
(that's the resolver's job).

What this module CAN'T discover at **Commission-author time** (before a
run starts):

  - **MCP-server tool lists.** Tools exposed by an MCP server (e.g.
    `mcp__github__create_issue`) are only knowable AFTER the agent
    connects to the server and runs `tools/list`. That happens at
    **agent-start time** — the translator captures it then via
    `ClaudeSDKClient.get_mcp_status()` and surfaces the live list on
    the corresponding `mcp_server_connected` events
    (`avp.mcp.tools[]`). For Commission authoring before a run, you'd need
    a side-channel handshake; out of scope for v0.1.

  - **Custom subagent contents.** We surface the subagent name (from the
    file name or its `name:` frontmatter) and source path. We do NOT
    parse the markdown frontmatter for description / system_prompt /
    tools. Authors who need that data should read the file themselves;
    keeps this module dependency-free (no YAML parser).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from avp_claude_agent.translator import (
    CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS,
    CLAUDE_CODE_PRESET_TOOLS,
)


@dataclass(frozen=True)
class SkillInfo:
    """One filesystem-discovered skill.

    `name` is the skill's directory name (or the explicit `name:`
    frontmatter field if you parse it yourself — we don't).
    `source_path` is the SKILL.md absolute path; pass to
    `Skill.avp_source` when building Commission.
    """

    name: str
    source_path: Path


@dataclass(frozen=True)
class SubagentInfo:
    """One filesystem-discovered subagent.

    `name` is the markdown file's stem (e.g. `code-reviewer.md` →
    `"code-reviewer"`). `source_path` is the absolute path. Authors
    needing the prompt/tools/model from frontmatter should read the
    file themselves.
    """

    name: str
    source_path: Path


@dataclass(frozen=True)
class Environment:
    """Snapshot of what's available at Commission-author time.

    `builtin_tools` and `builtin_subagents` are the SDK-runtime defaults
    we know from the documented surface. `filesystem_skills` and
    `filesystem_subagents` are walked from disk based on
    `setting_sources` (matching the SDK's own discovery convention).
    """

    builtin_tools: tuple[str, ...]
    builtin_subagents: tuple[str, ...]
    filesystem_skills: list[SkillInfo] = field(default_factory=list)
    filesystem_subagents: list[SubagentInfo] = field(default_factory=list)


# Setting-source → directory under that source. Mirrors the SDK's own
# discovery rules: user sources live under `~/.claude/`, project sources
# under `<cwd>/.claude/`. See:
#   https://code.claude.com/docs/en/agent-sdk/skills
#   https://code.claude.com/docs/en/sub-agents


def _user_claude_dir() -> Path:
    return Path.home() / ".claude"


def _project_claude_dir(cwd: Path) -> Path:
    return cwd / ".claude"


def discover_environment(
    *,
    cwd: str | Path = ".",
    setting_sources: list[str] | None = None,
) -> Environment:
    """Walk the runtime environment and return what's discoverable.

    `setting_sources` follows the Claude Agent SDK convention — pass
    a list containing any of `"user"` and `"project"`. Defaults to
    `["user", "project"]` (the SDK's own default when `setting_sources`
    is unset). To skip filesystem walking entirely, pass `[]` — only
    the SDK-bundled built-ins come back.

    `cwd` is the project root (where to look for `.claude/skills/` and
    `.claude/agents/`). Defaults to the current working directory.
    """
    sources = setting_sources if setting_sources is not None else ["user", "project"]
    cwd_path = Path(cwd).resolve()

    skill_dirs: list[Path] = []
    agent_dirs: list[Path] = []
    if "user" in sources:
        user = _user_claude_dir()
        skill_dirs.append(user / "skills")
        agent_dirs.append(user / "agents")
    if "project" in sources:
        project = _project_claude_dir(cwd_path)
        skill_dirs.append(project / "skills")
        agent_dirs.append(project / "agents")

    skills: list[SkillInfo] = []
    for skill_dir in skill_dirs:
        skills.extend(_walk_skills(skill_dir))

    subagents: list[SubagentInfo] = []
    for agent_dir in agent_dirs:
        subagents.extend(_walk_subagents(agent_dir))

    return Environment(
        builtin_tools=CLAUDE_CODE_PRESET_TOOLS,
        builtin_subagents=CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS,
        filesystem_skills=skills,
        filesystem_subagents=subagents,
    )


def _walk_skills(skills_dir: Path) -> list[SkillInfo]:
    """Each skill is a directory containing SKILL.md (per the
    agentskills.io convention the Claude Agent SDK follows). Skip the
    parent directory if it doesn't exist; honest-empty beats raising."""
    if not skills_dir.is_dir():
        return []
    out: list[SkillInfo] = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        out.append(SkillInfo(name=entry.name, source_path=skill_md))
    return out


def _walk_subagents(agents_dir: Path) -> list[SubagentInfo]:
    """Each subagent is a `<name>.md` markdown file (per the SDK's
    filesystem-based subagent convention). The name is the file stem."""
    if not agents_dir.is_dir():
        return []
    out: list[SubagentInfo] = []
    for entry in sorted(agents_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix != ".md":
            continue
        out.append(SubagentInfo(name=entry.stem, source_path=entry))
    return out
