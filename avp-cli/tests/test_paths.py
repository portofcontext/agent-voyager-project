"""`paths`'s docstring tree names every file and directory the module defines,
so the tree can't go stale. `test_eval_cli` checks a real eval's layout."""

import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest

from avp_cli import paths

TREE = paths.__doc__ or ""


def test_the_tree_names_every_file_name() -> None:
    names = [v for k, v in vars(paths).items() if k.isupper() and isinstance(v, str)]
    assert names
    for name in names:
        assert f" {name}" in TREE, name


def test_the_tree_names_every_path_under_the_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    functions = [
        f
        for name, f in vars(paths).items()
        if inspect.isfunction(f) and name not in ("home", "stamped")
    ]
    for function in functions:
        arguments = ["<name>"] * len(inspect.signature(function).parameters)
        relative = function(*arguments).relative_to(tmp_path)
        assert relative.name in TREE, function.__name__


def test_stamped_sorts_by_start_time() -> None:
    started = datetime(2026, 11, 3, 14, 25, 1, tzinfo=UTC)
    assert paths.stamped("capitals", started) == "20261103T142501Z-capitals"
