"""Refresh vendored ATIF models from a checkout at the pinned Harbor revision."""

import argparse
import subprocess
from pathlib import Path

REVISION = "9c7a39b991d7e2205019f6be0598cbd22d84bfc3"
ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.checkout, text=True
    ).strip()
    if revision != REVISION:
        parser.error(f"checkout must be at {REVISION}")
    target = ROOT / "avp-sdk/python/src/avp/_vendor/atif"
    for source in (args.checkout / "src/harbor/models/trajectories").glob("*.py"):
        (target / source.name).write_text(
            source.read_text().replace("harbor.models.trajectories", "avp._vendor.atif")
        )
    (target / "LICENSE").write_bytes((args.checkout / "LICENSE").read_bytes())


if __name__ == "__main__":
    main()
