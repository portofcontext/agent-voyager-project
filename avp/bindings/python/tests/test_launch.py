"""Launcher environment crosses a real process boundary without changing its parent."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from avp.launch import directory_env, local_environment


@pytest.mark.parametrize("crash", [False, True])
def test_launch_owns_only_its_state(tmp_path, monkeypatch, crash):
    ambient = tmp_path / "ambient"
    for name in directory_env(ambient):
        monkeypatch.setenv(name, str(ambient / name))
    persistent = tmp_path / "persistent-codex"
    persistent.mkdir()
    marker = persistent / "session"
    marker.write_text("keep")
    parent = dict(os.environ)
    root = None
    try:
        with local_environment(
            {"CODEX_HOME": str(persistent), "TEST_CREDENTIAL": "fixture"}
        ) as env:
            root = Path(env["AVP_ENV_ROOT"])
            result = subprocess.run(
                [sys.executable, "-c", "import os,json; print(json.dumps(dict(os.environ)))"],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            seen = json.loads(result.stdout)
            for name in directory_env(root):
                if name != "CODEX_HOME":
                    assert Path(seen[name]).is_relative_to(root)
                assert Path(seen[name]).is_dir()
            assert seen["CODEX_HOME"] == str(persistent)
            assert seen["TEST_CREDENTIAL"] == "fixture"
            assert dict(os.environ) == parent
            if crash:
                raise RuntimeError("scripted crash")
    except RuntimeError:
        assert crash
    assert root is not None and not root.exists()
    assert marker.read_text() == "keep"
    assert dict(os.environ) == parent
