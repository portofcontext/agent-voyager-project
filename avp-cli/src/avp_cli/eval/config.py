"""From the eval file to what the engine runs: `EvalConfig.from_eval` reads
and checks everything the file names, and returns an `EvalConfig`, which holds the
scorer's callable and yields each run's Commission. Conformance builds an
`EvalConfig` directly, with its case's check as the scorer."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from pydantic import JsonValue, ValidationError

from avp.commission import Commission
from avp_cli.eval.commission import EvalError, build, read
from avp_cli.eval.schemas import Eval, Item, JsonObject, ScorerSpec
from avp_cli.eval.scorers import SCORERS
from avp_cli.eval.scoring import Run, Scorer
from avp_cli.eval.template import Reference, TemplateError, check, references


class EvalCase(NamedTuple):
    """One run of an eval: a Commission, on an agent, for an item."""

    commission: str
    """The Commission's name."""
    agent: str
    item: Item
    built: Commission
    """The Commission sent: filled from the item, with avp's `run_id`."""


@dataclass(frozen=True)
class EvalConfig:
    name: str
    agents: list[str]
    commissions: dict[str, JsonObject]
    """The Commissions by name, before their placeholders are filled. Each
    fills to a valid Commission for every item."""
    dataset: list[Item]
    scorer: Scorer
    scorer_config: JsonObject = field(default_factory=dict)
    """The scorer's fields, filled from `item` and `run` for each run and
    passed to the scorer as `config`."""

    def __iter__(self) -> Iterator[EvalCase]:
        """Every Commission, on every agent, for every item."""
        for name, template in self.commissions.items():
            for agent in self.agents:
                for item in self.dataset:
                    run_id = f"{name}-{agent}-{item.id}"
                    yield EvalCase(name, agent, item, build(template, item, run_id))

    @classmethod
    def from_eval(cls, eval: Eval, base: Path, agents: list[str] | None = None) -> "EvalConfig":
        """The eval, ready to run. `base` is the eval file's directory, and
        `agents`, when given, overrides the eval's agents. Raises EvalError
        with every problem found."""
        problems: list[str] = []
        chosen = agents or eval.agents or []
        if not chosen:
            problems.append("no agents: the eval names none, and none were given")
        commissions: dict[str, JsonObject] = {}
        for name, source in eval.commissions.items():
            try:
                commissions[name] = read(source, base)
            except EvalError as error:
                problems.append(f"commission.{name}: {error}")
                continue
            problems += _commission_problems(name, commissions[name], eval.dataset)
        scorer = _scorer(eval.scorer, eval.dataset, base, problems)
        if problems or scorer is None:
            raise EvalError(*problems)
        return cls(eval.name, chosen, commissions, eval.dataset, scorer, eval.scorer.config)


def _commission_problems(name: str, template: JsonObject, dataset: list[Item]) -> list[str]:
    """Builds and validates the Commission for every item."""
    where = f"commission.{name}"
    problems = []
    for item in dataset:
        try:
            build(template, item, f"{name}-{item.id}", where)
        except TemplateError as error:
            problems.append(f"item {item.id}, {error}")
        except ValidationError as error:
            problems.extend(
                f"item {item.id}, {'.'.join([where, *map(str, e['loc'])])}: {e['msg']}"
                for e in error.errors()
            )
    return problems


def _scorer(
    spec: ScorerSpec, dataset: list[Item], base: Path, problems: list[str]
) -> Scorer | None:
    """The scorer's callable, after checking its fields and placeholders."""
    config = SCORERS.get(spec.name)
    if config is None:
        known = ", ".join(sorted(SCORERS)) or "none yet"
        problems.append(f"scorer.name: no scorer named {spec.name!r} (the scorers: {known})")
        return None
    try:
        config.model_validate(spec.config)
    except ValidationError as error:
        problems.extend(
            f"{'.'.join(['scorer', *map(str, e['loc'])])}: {e['msg']}" for e in error.errors()
        )
    try:
        found = references(spec.config, "scorer")
    except TemplateError as error:
        problems.append(str(error))
        return None
    for reference in found:
        problems += _reference_problems(reference, dataset)
    return config.scorer(base)


def _reference_problems(reference: Reference, dataset: list[Item]) -> list[str]:
    """An `item` placeholder must fill from every item. A `run` placeholder
    must name a field of the run; `run.item.…` is checked as `item.…`."""
    if reference.namespace == "run":
        first, _, rest = reference.path.partition(".")
        if first not in Run.model_fields:
            return [f"{reference.where}: run has no field {first!r}"]
        if first != "item" or not rest:
            return []
        reference = Reference("item", rest, reference.whole, reference.where)
    problems = []
    for item in dataset:
        scope: dict[str, JsonValue] = {"item": item.model_dump(mode="json")}
        try:
            check(reference, scope)
        except TemplateError as error:
            problems.append(f"item {item.id}, {error}")
    return problems
