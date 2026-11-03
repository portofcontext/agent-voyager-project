"""The shared SDK data directory is the inventory each package must bundle."""

import os
from pathlib import Path

SDK = Path(__file__).resolve().parent.parent / "avp-sdk"
DATA = SDK / "data"
PACKAGE_DATA = {
    "python": SDK / "python/src/avp/utils/data",
    "rust": SDK / "rust/src/utils/data",
}


def sync_links() -> None:
    """Link every shared JSON file into each SDK's package data directory."""
    for directory in PACKAGE_DATA.values():
        directory.mkdir(parents=True, exist_ok=True)
        for source in DATA.glob("*.json"):
            link = directory / source.name
            target = os.path.relpath(source, directory)
            if link.is_symlink() and link.readlink() == Path(target):
                continue
            if link.exists() or link.is_symlink():
                raise FileExistsError(f"unexpected SDK data file: {link}")
            link.symlink_to(target)
