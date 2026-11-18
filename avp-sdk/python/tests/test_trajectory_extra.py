"""The vendored ATIF models type every `extra` with AVP's extras."""

import inspect

import pytest

from avp._trajectory_extra import EXTRAS, Extra
from avp._vendor import atif
from avp.trajectory import parse_trajectory


def _models():
    return [m for _, m in inspect.getmembers(atif, inspect.isclass) if "extra" in m.model_fields]


def test_every_vendored_extra_is_typed() -> None:
    for model in _models():
        assert model.__name__ in EXTRAS, f"add {model.__name__} to EXTRAS"
        annotation = model.model_fields["extra"].annotation
        assert EXTRAS[model.__name__] | None == annotation, model.__name__
    assert issubclass(EXTRAS["Trajectory"], Extra)


def _document(**extra):
    return {
        "schema_version": "ATIF-v1.8",
        "session_id": "s",
        "agent": {"name": "a", "version": "1"},
        "steps": [{"step_id": 1, "source": "system", "message": "boom", **extra}],
    }


def test_plain_atif_and_other_keys_are_accepted() -> None:
    trajectory = parse_trajectory(_document(extra={"vendor": {"x": 1}}))
    assert trajectory.steps[0].extra["vendor"] == {"x": 1}
    assert "avp" not in trajectory.steps[0].extra


def test_unknown_error_codes_read_as_unknown() -> None:
    step = parse_trajectory(_document(extra={"avp": {"error_code": "later", "new": 1}})).steps[0]
    assert step.extra["avp"].error_code == "unknown"
    assert step.extra.avp.model_extra == {"new": 1}


def test_required_trajectory_fields() -> None:
    document = _document()
    document["extra"] = {"avp": {"avp_version": "0.1"}}
    with pytest.raises(ValueError, match="stop_reason"):
        parse_trajectory(document)
