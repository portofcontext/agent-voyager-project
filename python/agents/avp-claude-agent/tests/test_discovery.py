"""Discovery API: helps Commission authors see what's available before
writing `cfg.allowed_tools` / `cfg.subagents` / `cfg.skills`.

Two layers:
  - Public constants (CLAUDE_CODE_PRESET_TOOLS,
    CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS) — names known statically from
    the SDK / Claude Code documented surface.
  - `discover_environment()` — walks the filesystem the same way the
    SDK does to enumerate user/project skills and custom subagents.

Tests use tmp_path to build realistic .claude/skills/ and .claude/agents/
trees, plus monkeypatch HOME to isolate from the dev's actual machine.
"""

from __future__ import annotations

from avp_claude_agent import (
    CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS,
    CLAUDE_CODE_PRESET_TOOLS,
    Environment,
    discover_environment,
)

# ── Public constants ─────────────────────────────────────────────────────


def test_preset_tools_is_re_exported() -> None:
    """Commission authors can `from avp_claude_agent import CLAUDE_CODE_PRESET_TOOLS`
    and use it directly."""
    assert isinstance(CLAUDE_CODE_PRESET_TOOLS, tuple)
    assert "Read" in CLAUDE_CODE_PRESET_TOOLS
    assert "Write" in CLAUDE_CODE_PRESET_TOOLS
    assert "Bash" in CLAUDE_CODE_PRESET_TOOLS


def test_builtin_subagents_is_re_exported() -> None:
    assert CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS == ("general-purpose",)


# ── discover_environment: builtins always present ───────────────────────


def test_returns_builtins_even_when_no_filesystem(tmp_path, monkeypatch) -> None:
    """No skills, no agents on disk — built-in tool/subagent constants
    still come back. The SDK exposes them regardless of filesystem state."""
    monkeypatch.setenv("HOME", str(tmp_path))
    env = discover_environment(cwd=tmp_path)
    assert isinstance(env, Environment)
    assert env.builtin_tools == CLAUDE_CODE_PRESET_TOOLS
    assert env.builtin_subagents == CLAUDE_AGENT_SDK_BUILTIN_SUBAGENTS
    assert env.filesystem_skills == []
    assert env.filesystem_subagents == []


def test_empty_setting_sources_skips_filesystem_walk(tmp_path, monkeypatch) -> None:
    """`setting_sources=[]` means "don't load from user OR project."
    Filesystem entries should be empty even if .claude/skills/ exists."""
    monkeypatch.setenv("HOME", str(tmp_path))
    project_skills = tmp_path / ".claude" / "skills" / "should-be-ignored"
    project_skills.mkdir(parents=True)
    (project_skills / "SKILL.md").write_text("")
    env = discover_environment(cwd=tmp_path, setting_sources=[])
    assert env.filesystem_skills == []


# ── Filesystem skills ────────────────────────────────────────────────────


def test_discovers_project_skills(tmp_path, monkeypatch) -> None:
    """Each `<cwd>/.claude/skills/<name>/SKILL.md` becomes one SkillInfo."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project_skills_root = tmp_path / ".claude" / "skills"
    for skill_name in ["style-guide", "summarize-changes"]:
        sd = project_skills_root / skill_name
        sd.mkdir(parents=True)
        (sd / "SKILL.md").write_text("---\nname: " + skill_name + "\n---\nbody")

    env = discover_environment(cwd=tmp_path)
    names = sorted(s.name for s in env.filesystem_skills)
    assert names == ["style-guide", "summarize-changes"]
    # Source paths point to SKILL.md absolute paths.
    for skill in env.filesystem_skills:
        assert skill.source_path.is_file()
        assert skill.source_path.name == "SKILL.md"
        assert skill.source_path.is_absolute()


def test_discovers_user_skills_via_home(tmp_path, monkeypatch) -> None:
    """User skills live under `~/.claude/skills/`. Monkeypatch HOME so
    the test sees a controlled directory rather than the dev's
    real ~/.claude/."""
    monkeypatch.setenv("HOME", str(tmp_path))
    user_skills = tmp_path / ".claude" / "skills" / "user-only"
    user_skills.mkdir(parents=True)
    (user_skills / "SKILL.md").write_text("")

    env = discover_environment(cwd=tmp_path / "different-project")
    assert any(s.name == "user-only" for s in env.filesystem_skills)


def test_skips_skill_directory_without_skill_md(tmp_path, monkeypatch) -> None:
    """A directory under `.claude/skills/` without a SKILL.md isn't a
    valid skill — skip it. (Honest-empty: don't surface a name we can't
    point at a SKILL.md for.)"""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    incomplete = tmp_path / ".claude" / "skills" / "incomplete"
    incomplete.mkdir(parents=True)
    # No SKILL.md inside.
    env = discover_environment(cwd=tmp_path)
    assert all(s.name != "incomplete" for s in env.filesystem_skills)


def test_skips_files_at_skills_root(tmp_path, monkeypatch) -> None:
    """`.claude/skills/foo.txt` (a file, not a directory) shouldn't be
    treated as a skill."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    skills_root = tmp_path / ".claude" / "skills"
    skills_root.mkdir(parents=True)
    (skills_root / "stray.txt").write_text("not a skill")
    env = discover_environment(cwd=tmp_path)
    assert env.filesystem_skills == []


# ── Filesystem subagents ─────────────────────────────────────────────────


def test_discovers_project_subagents(tmp_path, monkeypatch) -> None:
    """Each `<cwd>/.claude/agents/<name>.md` becomes one SubagentInfo."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    agents_root = tmp_path / ".claude" / "agents"
    agents_root.mkdir(parents=True)
    (agents_root / "code-reviewer.md").write_text("---\n---\nbody")
    (agents_root / "test-agent.md").write_text("---\n---\nbody")

    env = discover_environment(cwd=tmp_path)
    names = sorted(s.name for s in env.filesystem_subagents)
    assert names == ["code-reviewer", "test-agent"]


def test_skips_non_md_files_in_agents_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    agents_root = tmp_path / ".claude" / "agents"
    agents_root.mkdir(parents=True)
    (agents_root / "real.md").write_text("")
    (agents_root / "ignored.txt").write_text("")
    (agents_root / "ignored.yaml").write_text("")

    env = discover_environment(cwd=tmp_path)
    names = [s.name for s in env.filesystem_subagents]
    assert names == ["real"]


# ── End-to-end usage pattern ─────────────────────────────────────────────


def test_environment_can_be_used_to_inform_commission_authoring(tmp_path, monkeypatch) -> None:
    """The motivating use case: a Commission author calls `discover_environment`
    to understand what skills/subagents are on disk, then makes deployment
    decisions about which to expose. In the refs-only Commission model the
    skills themselves are managed via opaque refs (resolved at run-time);
    filesystem discovery here is purely informational for the supervisor's
    deployment layer."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project_skills = tmp_path / ".claude" / "skills" / "deploy"
    project_skills.mkdir(parents=True)
    (project_skills / "SKILL.md").write_text("---\nname: deploy\n---\nbody")

    env = discover_environment(cwd=tmp_path)
    # The discovery surfaces the filesystem skill so the supervisor can
    # decide what to mount into the agent's workspace.
    assert any(s.name == "deploy" for s in env.filesystem_skills)
    # The env's full builtin list is also accessible — useful for picking
    # which built-ins to allowlist in `enabled_builtin_tools`.
    assert "Read" in env.builtin_tools
    assert "Bash" in env.builtin_tools
