"""Capture temporary adapter-test trajectories for the cross-SDK ATIF check."""

import hashlib
import os
import shutil
from pathlib import Path

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item):
    destination = os.environ.get("AVP_ATIF_CAPTURE")
    temporary = item.funcargs.get("tmp_path")
    if not destination or temporary is None:
        return
    for name in ("trajectory.json", "t.json"):
        source = temporary / name
        if source.is_file():
            identity = f"{item.path}:{item.nodeid}:{name}"
            target = Path(destination) / f"{hashlib.sha256(identity.encode()).hexdigest()}.json"
            shutil.copyfile(source, target)
