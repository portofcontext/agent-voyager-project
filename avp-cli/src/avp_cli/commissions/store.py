"""Named Commission files under AVP_HOME, with the same path syntax as evals."""

import json
import re
from pathlib import Path

from pydantic import JsonValue

from avp_cli import paths
from avp_cli.console import Failed

NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")


def check_name(name: str) -> None:
    if not NAME.fullmatch(name) or name.endswith(".json"):
        raise Failed(
            "a Commission name uses lowercase letters, numbers, ., _, or -; "
            "starts with a letter or number; and must not end in .json"
        )


def resolve(source: str, base: Path = Path(".")) -> Path:
    if "/" in source or source.endswith(".json"):
        return base / Path(source).expanduser()
    check_name(source)
    path = paths.commissions() / f"{source}.json"
    if not path.is_file():
        raise Failed(
            f"no saved Commission {source!r}; `avp commission list` shows them; "
            "use ./ for a file path"
        )
    return path


def read(path: Path) -> dict[str, JsonValue]:
    duplicates: set[str] = set()

    def object_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for key, value in pairs:
            if key in result:
                duplicates.add(key)
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(), object_pairs_hook=object_pairs)
    except (OSError, UnicodeError) as error:
        raise Failed(f"can't read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise Failed(f"{path} isn't JSON: {error}") from error
    if duplicates:
        raise Failed(f"{path} repeats JSON keys: {', '.join(map(repr, sorted(duplicates)))}")
    if not isinstance(value, dict):
        raise Failed(f"{path} isn't a JSON object")
    return value


def reusable(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {key: item for key, item in value.items() if key not in {"run_id", "supervisor"}}


def save(name: str, value: dict[str, JsonValue], replace: bool = False) -> Path:
    check_name(name)
    path = paths.commissions() / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w" if replace else "x") as file:
            file.write(json.dumps(reusable(value), indent=2) + "\n")
    except FileExistsError:
        raise Failed(f"Commission {name!r} already exists; use --force to replace it") from None
    except OSError as error:
        raise Failed(f"can't save {path}: {error}") from error
    return path


def names() -> list[str]:
    return sorted(path.stem for path in paths.commissions().glob("*.json") if path.is_file())


def delete(name: str) -> None:
    check_name(name)
    path = resolve(name)
    try:
        path.unlink()
    except OSError as error:
        raise Failed(f"can't delete {path}: {error}") from error
