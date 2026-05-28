"""The task an eval runs over: a `Dataset` of `Item`s.

An item is one task instance. `prompt` is the input handed to the agent (it
becomes the Commission's prompt, possibly via a setup's `prompt_template`).
`expected` is whatever the scorer compares the agent's answer against: a string
for exact-match, a dict of required keys for structural-match, or anything a
custom scorer understands.

Keep datasets small. The whole matrix is `len(setups) * len(items)` real agent
runs, each a subprocess against a model, so a 3-setup, 5-item eval is 15 paid
runs. The bundled demo ships 3 items on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Item:
    id: str
    prompt: str
    expected: Any = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Dataset:
    name: str
    items: list[Item]

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)
