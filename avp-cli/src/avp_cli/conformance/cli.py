"""`avp conformance check` and `avp conformance list`."""

import shlex
from dataclasses import asdict
from typing import Annotated

import typer
from rich.table import Table

from avp_cli import console
from avp_cli._cli_common import AgentOption, JsonOption, VerboseOption
from avp_cli.conformance import check as checking
from avp_cli.conformance import mock
from avp_cli.conformance.cases import CASES, Case
from avp_cli.conformance.rules import RULES
from avp_cli.console import Failed, out
from avp_cli.runs import volumes

app = typer.Typer(
    no_args_is_help=True, help="Check that an agent follows the spec's rules for agents."
)

RuleOption = Annotated[
    list[str] | None, typer.Option("--rule", help="Only this rule's cases, such as commission.5.1.")
]
DEFAULT_MODEL = "anthropic/claude-haiku-4-5"
STYLES = {"pass": "green", "fail": "red", "skip": "yellow"}


@app.command()
def check(
    agent: AgentOption,
    rule: RuleOption = None,
    case: Annotated[list[str] | None, typer.Option(help="Only this case.")] = None,
    concurrency: Annotated[int, typer.Option(min=1, help="How many runs at once.")] = 1,
    volume: Annotated[
        list[str] | None,
        typer.Option(
            "--volume", "-v", help="HOST:SANDBOX[:ro] to mount a host path in every sandbox."
        ),
    ] = None,
    entrypoint: Annotated[
        str | None,
        typer.Option(help="Run the agent with this command line, not the image's ENTRYPOINT."),
    ] = None,
    model: Annotated[
        str, typer.Option(help="The model each Commission names, as provider/model.")
    ] = DEFAULT_MODEL,
    mock_image: Annotated[
        str, typer.Option(help="The aimock image for the mock model, instead of the pinned one.")
    ] = mock.IMAGE,
    json: JsonOption = False,
    verbose: VerboseOption = False,
) -> None:
    """Run the cases against an agent and report pass, fail, or skip by rule.
    Exits 1 when a MUST case fails."""
    console.set_verbose(verbose)
    chosen = _cases(rule, case)
    outcomes = checking.check(
        agent,
        chosen,
        checking.model(model),
        concurrency,
        volumes.parse(volume or []),
        _command_line(entrypoint),
        mock_image,
    )
    if json:
        out.print_json(
            data=[
                {**asdict(o), "run_directory": str(o.run_directory) if o.run_directory else None}
                for o in outcomes
            ]
        )
    else:
        table = Table("Rule", "Case", "Level", "Result", "Why")
        for o in outcomes:
            why = "\n".join(o.reasons)
            if o.status == "fail" and o.run_directory:
                why += f"\nRun: {o.run_directory}"
            table.add_row(o.rule, o.case, o.level, f"[{STYLES[o.status]}]{o.status}[/]", why or "-")
        out.print(table)
    if any(o.status == "fail" and o.level == "MUST" for o in outcomes):
        raise typer.Exit(1)


@app.command("list")
def list_rules(rule: RuleOption = None) -> None:
    """List the rules for agents and the cases for each."""
    _check_rules(rule)
    table = Table("Rule", "Title", "Cases")
    for rule_id, title in RULES.items():
        if rule and rule_id not in rule:
            continue
        names = [c.name for c in CASES if c.rule == rule_id]
        table.add_row(rule_id, title, "\n".join(names) or "[dim]none yet[/]")
    out.print(table)


def _command_line(entrypoint: str | None) -> list[str] | None:
    if entrypoint is None:
        return None
    try:
        words = shlex.split(entrypoint)
    except ValueError as error:
        raise Failed(f"--entrypoint {entrypoint!r}: {error}") from None
    if not words:
        raise Failed("--entrypoint is empty")
    return words


def _check_rules(rules: list[str] | None) -> None:
    unknown = sorted(set(rules or []) - set(RULES))
    if unknown:
        raise Failed(f"no rule {', '.join(unknown)}. `avp conformance list` shows them")


def _cases(rules: list[str] | None, names: list[str] | None) -> list[Case]:
    _check_rules(rules)
    missing = sorted(set(names or []) - {c.name for c in CASES})
    if missing:
        raise Failed(f"no case {', '.join(missing)}. `avp conformance list` shows them")
    chosen = [c for c in CASES if (not rules or c.rule in rules) and (not names or c.name in names)]
    if not chosen:
        raise Failed("no case matches; `avp conformance list` shows which rules have cases")
    return chosen
