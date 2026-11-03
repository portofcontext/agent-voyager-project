"""The eval file, `<name>.eval.json`: which agents run which Commissions on
which items, and how each run is scored. It is avp's own format, not an AVP
wire spec, so it versions on its own in `eval_version`. See docs/eval.md.

Paths in the file are relative to the file, so an eval and its Commissions can
be committed together."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
    PlainSerializer,
    PlainValidator,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

NAME = r"^[a-z0-9][a-z0-9._-]*$"
Name = Annotated[str, StringConstraints(pattern=NAME)]
"""Lowercase, as an installed agent's name is, so it can name a directory."""


@dataclass(frozen=True)
class NamedCommission:
    """A Commission saved in avp, by the name `avp commission list` shows."""

    name: str


@dataclass(frozen=True)
class CommissionFile:
    """A Commission's JSON file, relative to the eval file."""

    path: Path


JsonObject = dict[str, JsonValue]

CommissionSource = NamedCommission | CommissionFile | JsonObject
"""Where a run's Commission comes from. An inline Commission stays as a JSON
object until its placeholders are filled, and is validated after."""

_object = TypeAdapter(JsonObject)


def _source(value: Any) -> CommissionSource:
    """A string is a reference: a path when it has a `/` or ends in `.json`,
    otherwise a saved Commission's name. Anything else is inline."""
    if isinstance(value, NamedCommission | CommissionFile):
        return value
    if isinstance(value, str):
        if "/" in value or value.endswith(".json"):
            return CommissionFile(Path(value))
        if not re.match(NAME, value):
            raise ValueError(
                f"{value!r} is neither a saved Commission's name nor a path to a .json file"
            )
        return NamedCommission(value)
    if not isinstance(value, dict):
        raise ValueError("an inline Commission must be a JSON object")
    return _object.validate_python(value)


def _dump(source: CommissionSource) -> JsonValue:
    match source:
        case NamedCommission():
            return source.name
        case CommissionFile():
            return str(source.path)
    return source


CommissionField = Annotated[
    CommissionSource, PlainValidator(_source), PlainSerializer(_dump, return_type=JsonValue)
]


class Item(BaseModel):
    """One item in the dataset: an `id` and any other fields, which fill
    `{item.…}` placeholders."""

    model_config = ConfigDict(extra="allow")

    id: Name
    """Names the item's runs and its row on the scoreboard."""


def _repeated(names: list[str]) -> str:
    return ", ".join(sorted({n for n in names if names.count(n) > 1}))


def _unique(items: list[Item]) -> list[Item]:
    if repeated := _repeated([item.id for item in items]):
        raise ValueError(f"item IDs repeat: {repeated}")
    return items


def _one_or_more(value: Any) -> Any:
    return value if isinstance(value, list) else [value]


def _name(source: CommissionSource, position: int) -> str:
    """A Commission's name on the scoreboard and in its runs' IDs: its file's
    name without `.json`, its saved name, or `inline-<position>`, counted
    from 1."""
    match source:
        case NamedCommission():
            return source.name
        case CommissionFile():
            return source.path.stem
    return f"inline-{position}"


class ScorerSpec(BaseModel):
    """The eval file's `scorer`: `name` picks the scorer, and its other
    fields configure it. They're checked against the scorer's own fields when
    the eval is rendered."""

    model_config = ConfigDict(extra="allow")

    name: str

    @property
    def config(self) -> JsonObject:
        """The fields other than `name`, placeholders and all."""
        return dict(self.__pydantic_extra__ or {})


class Eval(BaseModel):
    """One eval file. Unknown fields are errors, since they are more often
    typos than intent."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    eval_version: Literal["0.1"]
    """The eval format the file follows."""
    name: Name
    """Names the eval in `avp eval list` and its scoreboard."""
    agents: Annotated[list[Name], BeforeValidator(_one_or_more), Field(min_length=1)] | None = None
    """Installed agents to run, by name: one, or a list. Optional, since the
    agents can be given when the eval runs instead."""
    commission: Annotated[list[CommissionField], BeforeValidator(_one_or_more), Field(min_length=1)]
    """The Commission to run, or a list of them to compare, each given as a
    saved Commission's name, a path to its file, or inline. Every Commission
    runs on every agent; a Commission's own `agents` map holds its per-agent
    settings."""
    dataset: Annotated[list[Item], Field(min_length=1), AfterValidator(_unique)]
    """The items each Commission runs on."""
    scorer: ScorerSpec
    """How each run is scored."""

    @model_validator(mode="after")
    def _names(self) -> "Eval":
        names = [_name(s, n) for n, s in enumerate(self.commission, 1)]
        if invalid := [n for n in names if not re.match(NAME, n)]:
            raise ValueError(f"Commission files need lowercase names: {', '.join(invalid)}")
        if repeated := _repeated(names):
            raise ValueError(f"Commission names repeat: {repeated}")
        return self

    @property
    def commissions(self) -> dict[str, CommissionSource]:
        """The Commissions by name."""
        return {_name(s, n): s for n, s in enumerate(self.commission, 1)}
