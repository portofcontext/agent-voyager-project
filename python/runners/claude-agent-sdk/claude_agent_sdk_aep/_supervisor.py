"""supervise() — minimal helper to spawn an AEP runner and stream its events.

.. warning::
    **For development and demo use only.**  ``supervise()`` is a thin
    convenience wrapper intended for local experimentation, examples, and
    evals.  It is **not suitable for production** supervisors because it:

    - provides no error handling, retries, or backpressure
    - does not forward stdin to the subprocess (no hook round-trips)
    - silently drops lines that are not valid JSON
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Generator


def supervise(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict | None = None,
) -> Generator[dict, None, None]:
    """Spawn *cmd* and yield parsed AEP events from its stdout.

    **Development / demo use only** — see module docstring for caveats.

    Example::

        from claude_agent_sdk_aep import supervise

        for event in supervise([sys.executable, "my_agent.py"]):
            if event["type"] == "text_output":
                print(event["text"])
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env or os.environ.copy(),
    )
    for raw in proc.stdout:
        raw = raw.strip()
        if raw:
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                pass
    proc.wait()
