"""All actionable Commission diagnostics, including independent errors in bad files."""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal, TypeVar

from pydantic import JsonValue, TypeAdapter, ValidationError

from avp.commission import AgentSettings, EnvSecret, McpServer, McpServerHttp, Model, Skill
from avp.descriptor import AgentDescriptor
from avp.utils._skill_md import frontmatter_value
from avp_cli.commissions.prepare import prepare
from avp_cli.console import Failed, err

T = TypeVar("T")


@dataclass(frozen=True)
class Problem:
    level: Literal["error", "warning"]
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.where}: {self.message}"


def builtins(descriptor: AgentDescriptor) -> dict[str, list[str]]:
    return {
        "enabled_tools": [t.name for t in descriptor.tools or [] if t.mcp_server_id is None],
        "enabled_subagents": [s.name for s in descriptor.subagents or []],
        "enabled_skills": [s.name for s in descriptor.skills or []],
        "enabled_mcp_servers": [s.id for s in descriptor.mcp_servers or []],
    }


def _valid(adapter: TypeAdapter[T], value: object) -> T | None:
    # The whole-model validation reports structural errors. Still check each
    # usable component so one malformed item doesn't hide unrelated problems.
    try:
        return adapter.validate_python(value)
    except ValidationError:
        return None


def _items(value: JsonValue) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def _duplicates(values: list[str], where: str) -> list[Problem]:
    return [
        Problem("error", where, f"duplicate {name!r}")
        for name, count in Counter(values).items()
        if count > 1
    ]


def check(value: dict[str, JsonValue], descriptor: AgentDescriptor | None = None) -> list[Problem]:
    problems: list[Problem] = []
    try:
        prepare(value, "check")
    except ValidationError as error:
        problems.extend(
            Problem("error", ".".join(map(str, e["loc"])), e["msg"]) for e in error.errors()
        )

    servers = [
        (i, s)
        for i, raw in enumerate(_items(value.get("mcp_servers")))
        if (s := _valid(TypeAdapter(McpServer), raw)) is not None
    ]
    skills = [
        (i, s)
        for i, raw in enumerate(_items(value.get("skills")))
        if (s := _valid(TypeAdapter(Skill), raw)) is not None
    ]
    problems += _duplicates([s.id for _, s in servers], "mcp_servers.id")
    problems += _duplicates([s.name for _, s in skills], "skills.name")
    for i, skill in skills:
        name = frontmatter_value(skill.files["SKILL.md"], "name")
        if name != skill.name:
            problems.append(
                Problem(
                    "error",
                    f"skills.{i}.name",
                    f"{skill.name!r} differs from SKILL.md name {name!r}",
                )
            )

    secrets: list[tuple[str, EnvSecret]] = []
    model = _valid(TypeAdapter(Model), value.get("model"))
    if model and isinstance(model.credential, EnvSecret):
        secrets.append(("model.credential", model.credential))
    for i, server in servers:
        field = "headers" if isinstance(server, McpServerHttp) else "env"
        entries = server.headers if isinstance(server, McpServerHttp) else server.env
        if isinstance(server, McpServerHttp):
            problems += _duplicates(
                [key.lower() for key in entries or {}], f"mcp_servers.{i}.headers"
            )
        secrets.extend(
            (f"mcp_servers.{i}.{field}.{key}", secret)
            for key, secret in (entries or {}).items()
            if isinstance(secret, EnvSecret)
        )
    problems.extend(
        Problem(
            "warning",
            where,
            f"env secret {secret.env!r} is visible to the agent; "
            "pass it with --env or --env-file; prefer proxy when available",
        )
        for where, secret in secrets
    )

    agents = value.get("agents")
    if descriptor is not None and isinstance(agents, dict) and descriptor.agent_name not in agents:
        problems.append(Problem("error", "agents", f"no entry for {descriptor.agent_name!r}"))
    for name, raw in agents.items() if isinstance(agents, dict) else []:
        settings = _valid(TypeAdapter(AgentSettings), raw)
        if settings is None:
            continue
        for field in (
            "enabled_tools",
            "enabled_subagents",
            "enabled_skills",
            "enabled_mcp_servers",
        ):
            problems += _duplicates(getattr(settings, field) or [], f"agents.{name}.{field}")
        if descriptor is None or name != descriptor.agent_name:
            continue
        if settings.version is not None and settings.version != descriptor.agent_version:
            problems.append(
                Problem(
                    "error",
                    f"agents.{name}.version",
                    f"{settings.version!r} differs from agent version {descriptor.agent_version!r}",
                )
            )
        for field, offered in builtins(descriptor).items():
            for unknown in sorted(set(getattr(settings, field) or []) - set(offered)):
                problems.append(
                    Problem(
                        "error", f"agents.{name}.{field}", f"agent has no built-in item {unknown!r}"
                    )
                )

    if descriptor is not None:
        for i, server in servers:
            if server.id in {s.id for s in descriptor.mcp_servers or []}:
                problems.append(
                    Problem(
                        "warning",
                        f"mcp_servers.{i}.id",
                        f"{server.id!r} clashes with a built-in MCP server",
                    )
                )
        for i, skill in skills:
            if skill.name in {s.name for s in descriptor.skills or []}:
                problems.append(
                    Problem(
                        "warning",
                        f"skills.{i}.name",
                        f"{skill.name!r} clashes with a built-in skill",
                    )
                )
        if (
            model
            and descriptor.supported_models is not None
            and not any(
                _matches(p.provider, model.provider) and _matches(p.id, model.id)
                for p in descriptor.supported_models
            )
        ):
            problems.append(
                Problem(
                    "warning", "model", f"{model.provider}/{model.id} is outside supported_models"
                )
            )
    return problems


def _matches(pattern: str, value: str) -> bool:
    return re.fullmatch(re.escape(pattern).replace(r"\*", ".*"), value, re.DOTALL) is not None


def require_valid(problems: list[Problem]) -> None:
    for problem in problems:
        if problem.level == "warning":
            err.print(str(problem), markup=False, highlight=False)
    errors = [str(p) for p in problems if p.level == "error"]
    if errors:
        raise Failed("\n".join(errors))
