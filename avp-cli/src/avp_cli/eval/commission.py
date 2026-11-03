"""From an eval file to the Commission each run is sent: read the
Commission, fill in the item's placeholders, and set what avp owns."""

import json
from importlib.metadata import version
from pathlib import Path

from pydantic import ValidationError

from avp.commission import Commission
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
    match source:
        case NamedCommission():
            raise EvalError(f"{source.name!r}: saved Commissions aren't supported yet; give a path")
        case CommissionFile():
            path = base / source.path
            try:
                commission = json.loads(path.read_text())
            except OSError as error:
                raise EvalError(f"can't read {path}: {error.strerror}") from error
            except json.JSONDecodeError as error:
                raise EvalError(f"{path} isn't JSON: {error}") from error
            if not isinstance(commission, dict):
                raise EvalError(f"{path} isn't a JSON object")
            return commission
    return source


def build(template: JsonObject, item: Item, run_id: str, where: str = "") -> Commission:
    """The run's Commission: `template` with `item` filled in, and avp's
    `run_id` and `supervisor`. Raises TemplateError or ValidationError."""
    commission = render(template, {"item": item.model_dump(mode="json")}, where)
    if not isinstance(commission, dict):
        raise TemplateError(f"{where}: the Commission isn't a JSON object once filled")
    commission["run_id"] = run_id
    commission["supervisor"] = {"name": "avp-cli", "version": version("avp-cli")}
    return Commission.model_validate(commission)
