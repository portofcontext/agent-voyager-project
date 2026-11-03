"""The built-in scorers, by the `name` an eval file's `scorer` gives. Each is
a ScorerConfig: its fields are the scorer's fields in the eval file. See
docs/eval.md, Scorers."""

from avp_cli.eval.scorers.match import Match
from avp_cli.eval.scoring import ScorerConfig

SCORERS: dict[str, type[ScorerConfig]] = {s.name: s for s in [Match]}
"""The built-in scorers by `name`."""

__all__ = ["SCORERS", "Match"]
