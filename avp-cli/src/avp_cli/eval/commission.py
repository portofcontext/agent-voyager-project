"""From an eval file to the Commission each run is sent: read the
Commission, fill in the item's placeholders, and set what avp owns."""

from pathlib import Path

from pydantic import ValidationError

from avp.commission import Commission
from avp_cli.commissions import store
from avp_cli.commissions.prepare import prepare
from avp_cli.console import Failed
from avp_cli.eval.schemas import (
    CommissionFile,
    CommissionSource,
    Eval,
    Item,
    JsonObject,
    NamedCommission,
)
from avp_cli.eval.template import TemplateError, render


class EvalError(Exception):
    """An eval that can't run, with every reason found."""

    def __init__(self, *problems: str) -> None:
        super().__init__("\n".join(problems))
        self.problems = list(problems)


def load(path: Path) -> Eval:
    try:
        return Eval.model_validate_json(path.read_text())
    except OSError as error:
        raise EvalError(f"can't read {path}: {error.strerror}") from error
    except ValidationError as error:
        raise EvalError(f"{path} isn't a valid eval:\n{error}") from error


def read(source: CommissionSource, base: Path) -> JsonObject:
    """The Commission as JSON, before its placeholders are filled. `base` is
    the eval file's directory."""
    try:
        match source:
            case NamedCommission():
                return store.read(store.resolve(source.name))
            case CommissionFile():
                return store.read(base / source.path.expanduser())
    except Failed as error:
        raise EvalError(str(error)) from error
    return source


def fill(template: JsonObject, item: Item, where: str = "") -> JsonObject:
    """Render caller-owned fields, before validation and dispatch identity."""
    commission = render(store.reusable(template), {"item": item.model_dump(mode="json")}, where)
    if not isinstance(commission, dict):
        raise TemplateError(f"{where}: the Commission isn't a JSON object once filled")
    return commission


def build(template: JsonObject, item: Item, run_id: str, where: str = "") -> Commission:
    """The run's Commission: `template` with `item` filled in, and avp's
    `run_id` and `supervisor`. Raises TemplateError or ValidationError."""
    return prepare(fill(template, item, where), run_id)
