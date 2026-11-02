"""`avp conformance check` and `avp conformance list`."""

from dataclasses import asdict
from typing import Annotated

import typer
from rich.table import Table

from avp_cli import console
from avp_cli.conformance import check as checking
from avp_cli.conformance.cases import CASES, Case
from avp_cli.conformance.rules import RULES
from avp_cli.console import Failed, VerboseOption, err, line, out

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
    agent: Annotated[str, typer.Option(help="An installed agent.")],
    rule: RuleOption = None,
    case: Annotated[list[str] | None, typer.Option(help="Only this case.")] = None,
    model: Annotated[
        str, typer.Option(help="The model each Commission names, as provider/model.")
    ] = DEFAULT_MODEL,
    json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
    verbose: VerboseOption = False,
) -> None:
    """Run the cases against an agent and report pass, fail, or skip by rule.
    Exits 1 when a MUST case fails."""
    console.set_verbose(verbose)
    chosen = _cases(rule, case)
    with err.status(line("Starting")) as status:
        outcomes = checking.check(
            agent, chosen, checking.model(model), lambda text: status.update(line(text))
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
    unknown = sorted(set(rule or []) - set(RULES))
    if unknown:
        raise Failed(f"no rule {', '.join(unknown)}. `avp conformance list` shows them")
    table = Table("Rule", "Title", "Cases")
    for rule_id, title in RULES.items():
        if rule and rule_id not in rule:
            continue
        names = [c.name for c in CASES if c.rule == rule_id]
        table.add_row(rule_id, title, "\n".join(names) or "[dim]none yet[/]")
    out.print(table)


def _cases(rules: list[str] | None, names: list[str] | None) -> list[Case]:
    unknown = sorted(set(rules or []) - set(RULES))
    if unknown:
        raise Failed(f"no rule {', '.join(unknown)}. `avp conformance list` shows them")
    missing = sorted(set(names or []) - {c.name for c in CASES})
    if missing:
        raise Failed(f"no case {', '.join(missing)}. `avp conformance list` shows them")
    chosen = [c for c in CASES if (not rules or c.rule in rules) and (not names or c.name in names)]
    if not chosen:
        raise Failed("no case matches; `avp conformance list` shows which rules have cases")
    return chosen
