"""A `Setup` pairs a commission id with its base wire `Commission`.

The library stores raw wire Commissions (`avp_cli.library`); a `Setup` is just
the in-memory pairing of one with its id, plus the eval-only logic that turns it
into a per-run Commission. That logic lives here, in code — never on disk:

  - `{input}` in the base `prompt` (a plain string) is replaced with the dataset
    case's text;
  - `run_id` is assigned per run;
  - the supervisor (avp-cli) is stamped;
  - a `commission:<id>` tag is appended for trajectory attribution.

`Setup` stays the internal class name; the user-facing noun is "commission".
"""

from __future__ import annotations

from dataclasses import dataclass

from avp.commission import Commission, SupervisorPreamble
from avp_cli.eval.dataset import Item

_SUPERVISOR = SupervisorPreamble(name="avp-cli", version="0.1.0")


@dataclass(frozen=True)
class Setup:
    """One commission under test: its id + the base wire Commission it runs.

    `agent` optionally binds the commission to a single agent (a registry name
    or manifest path). `None` means it runs on every agent in the eval (the
    default cross-product). Binding lets one eval give each agent a commission
    tuned for it, e.g. an `enabled_builtin_tools` allow-list expressed in that
    agent's own tool namespace.
    """

    id: str
    commission: Commission
    agent: str | None = None

    @property
    def model(self) -> str | None:
        return self.commission.model

    def render_prompt(self, item: Item) -> str:
        """The base prompt with `{input}` filled by the case (or the case verbatim)."""
        prompt = self.commission.prompt
        if prompt and "{input}" in prompt:
            return prompt.replace("{input}", item.prompt)
        return prompt or item.prompt

    def to_commission(
        self, item: Item, run_id: str, *, model_override: str | None = None
    ) -> Commission:
        """The concrete per-run wire Commission for one dataset case.

        A copy of the base with the per-run fields filled in; the on-disk base is
        untouched.
        """
        tags = [*(self.commission.tags or []), f"commission:{self.id}"]
        return self.commission.model_copy(
            update={
                "run_id": run_id,
                "prompt": self.render_prompt(item),
                "model": model_override or self.commission.model,
                "supervisor": _SUPERVISOR,
                "tags": tags,
            }
        )
