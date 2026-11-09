"""Where avp keeps its files, and what each is named.

avp's state lives under `$AVP_HOME`, or `~/.avp`:

    agents/<name>.json                   one installed agent
    commissions/<name>.json              one reusable Commission, without run identity
    runs/<time>-<run_id>/                a run directory, from `avp run`
    evals/<time>-<name>/                 one eval run
        eval.json                        the eval file, as given
        results.json                     each run's outcome and score
        agents/<name>.json               an agent's image and Descriptor, from one describe
        runs/<run_id>/                   a run directory
        share.json                       where the eval is shared, and the token that takes it down
    conformance/<time>-<agent>/          one `avp conformance check`, laid out as an eval run's
        agents/<name>.json               as above
        runs/<run_id>/                   as above
    vault.json                           secrets' names and descriptions, never their values
    opensandbox/
        config.toml                      the config the service was last started with
        state.db                         the service's database
        server.log                       the service's output
        server.pid                       the process avp started

A run directory, under `runs/` or in an eval's `runs/`, is mounted in the
sandbox at `/io`:

    commission.json                      the dispatched Commission, with fresh run identity
    trajectory.json                    the Trajectory the agent writes
    agent.stderr                         what the agent printed to stderr, when anything
    scorer-error.txt                     in an eval, why its scorer failed

`<time>` is the UTC start time, `20261103T142501Z`, so directories sort by when
they started.

This module only names paths. Reading, writing, and creating them belong to the
modules that use them: `agents.store` for agents; `runs.directory`,
and `runs.dispatch` for run directories; `conformance.check` for its directory; `eval.results`,
`eval.engine`, and `eval.scoring` for evals; `vault.store`; and
`sandbox.service`. A new file or directory gets its name here and its line in
the tree above, and its code in its module.
Functions under the home read `$AVP_HOME` when called, so tests can set it.
"""

import os
from datetime import datetime
from pathlib import Path

# ── run directory ──────────────────────────────────────────────────────────

COMMISSION = "commission.json"
TRAJECTORY = "trajectory.json"
STDERR = "agent.stderr"
SCORER_ERROR = "scorer-error.txt"

# ── eval directory ─────────────────────────────────────────────────────────

EVAL = "eval.json"
RESULTS = "results.json"
EVAL_RUNS = "runs"
"""One run directory per run, named by its `run_id`."""
EVAL_AGENTS = "agents"
SHARE = "share.json"
"""One `<name>.json` per agent: its image and Descriptor."""


def stamped(name: str, started: datetime) -> str:
    """`<time>-<name>`, the name of a run or eval directory under the home."""
    return f"{started.strftime('%Y%m%dT%H%M%SZ')}-{name}"


# ── under the home ─────────────────────────────────────────────────────────


def home() -> Path:
    return Path(os.environ.get("AVP_HOME") or Path.home() / ".avp")


def agents() -> Path:
    return home() / "agents"


def commissions() -> Path:
    return home() / "commissions"


def agent(name: str) -> Path:
    return agents() / f"{name}.json"


def runs() -> Path:
    return home() / "runs"


def evals() -> Path:
    return home() / "evals"


def conformance() -> Path:
    return home() / "conformance"


def vault() -> Path:
    return home() / "vault.json"


def opensandbox() -> Path:
    return home() / "opensandbox"


def opensandbox_config() -> Path:
    return opensandbox() / "config.toml"


def opensandbox_store() -> Path:
    return opensandbox() / "state.db"


def opensandbox_log() -> Path:
    return opensandbox() / "server.log"


def opensandbox_pid() -> Path:
    return opensandbox() / "server.pid"
