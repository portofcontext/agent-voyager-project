"""Real materialization smoke: run a bundled example env through uv and assert
the provisioned interpreter has its package and the seeded files landed.

Needs `uv` on PATH (skipped otherwise). This is the "run examples as smoke tests"
layer — it exercises the actual provisioner, not a stub.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from avp_cli import environment as env

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "environments"


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv on PATH")
def test_python_six_example_materializes(tmp_path) -> None:
    block = json.loads((EXAMPLES / "python-six.json").read_text())
    mat = env.materialize(env.Environment.parse(block), tmp_path / "env", base_dir=EXAMPLES)

    # files seeded into the workspace
    assert (mat.workspace / "README.md").read_text() == "seeded by avp env\n"

    # the provisioned interpreter actually has the package
    py = mat.prefix / "python" / "bin" / "python"
    r = subprocess.run(
        [str(py), "-c", "import six; print(six.__version__)"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()  # printed a version

    # launch facts the runner will use
    assert str(mat.prefix / "python" / "bin") in mat.path_additions
    assert mat.env_vars["VIRTUAL_ENV"].endswith("python")
    assert "api.anthropic.com" in mat.net
