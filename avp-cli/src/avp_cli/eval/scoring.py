"""Scoring: turn one run's final answer into a 0..1 score.

A `Scorer` looks at the item, the agent's extracted final output, and the run
facts, and returns a `Score`. Two numbers fall out of a scorer across a whole
dataset, and they are not the same thing:

  - accuracy  = mean of `score.value` (partial credit allowed)
  - pass_rate = share of items where `score.passed` is true

A setup can clear most items with rough answers (high pass_rate, middling
accuracy) or get most items partly right but few all the way (high accuracy,
low pass_rate). The board reports both.

`FinalOutput` is what the engine extracts from the trajectory and hands to the
scorer; the scorer never touches raw events. That keeps "scoring an answer"
separate from "reading the trajectory" (the two trajectory fact-classes in
`spec/v0.1/trajectory.md`). A scorer may still consult `Summary` if it wants to
reward efficiency (fewer turns, no tool errors).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from avp_cli.observability import Summary


@dataclass(frozen=True)
class FinalOutput:
    """The agent's answer, extracted from the trajectory by the engine."""

    text: str | None
    structured: dict[str, Any] | None
    stop_reason: str | None


@dataclass(frozen=True)
class Score:
    value: float  # 0.0 .. 1.0 for this item
    passed: bool
    detail: str = ""  # shown in the board's failures section


@runtime_checkable
class Scorer(Protocol):
    name: str

    def score(self, item: Any, output: FinalOutput, summary: Summary) -> Score: ...


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()


@dataclass
class ExactMatchScorer:
    """1.0 iff the answer text equals `item.expected` (whitespace/case normalized)."""

    name: str = "exact-match"

    def score(self, item: Any, output: FinalOutput, summary: Summary) -> Score:
        expected = "" if item.expected is None else str(item.expected)
        got = output.text or ""
        ok = _normalize(got) == _normalize(expected)
        if ok:
            return Score(value=1.0, passed=True)
        return Score(value=0.0, passed=False, detail=f"expected {expected!r}, got {got[:80]!r}")


@dataclass
class StructuralMatchScorer:
    """Fraction of `item.expected` (a dict) keys the answer got right.

    The agent's answer is parsed as JSON (`output.structured`). The value is the
    share of expected keys whose value matches; `passed` is value >= threshold.
    This is the scorer that makes accuracy and pass_rate diverge: an answer that
    nails 2 of 3 keys scores value 0.67 but, at threshold 1.0, does not pass.
    Numbers compare with a small tolerance so 2 and 2.0 match.
    """

    threshold: float = 1.0
    name: str = "structural-match"

    def score(self, item: Any, output: FinalOutput, summary: Summary) -> Score:
        expected = item.expected
        if not isinstance(expected, dict):
            raise TypeError("StructuralMatchScorer needs item.expected to be a dict")
        got = output.structured
        if got is None:
            return Score(
                value=0.0, passed=False, detail=f"answer was not JSON: {(output.text or '')[:80]!r}"
            )

        hits = 0
        misses: list[str] = []
        for key, want in expected.items():
            have = got.get(key)
            if _values_match(want, have):
                hits += 1
            else:
                misses.append(f"{key}: want {want!r} got {have!r}")
        value = hits / len(expected) if expected else 1.0
        detail = "" if not misses else "; ".join(misses)
        return Score(value=value, passed=value >= self.threshold, detail=detail)


def _values_match(want: Any, have: Any) -> bool:
    if isinstance(want, (int, float)) and isinstance(have, (int, float)):
        return abs(float(want) - float(have)) <= 1e-6
    if isinstance(want, str) and isinstance(have, str):
        return _normalize(want) == _normalize(have)
    return want == have


@dataclass
class FidelityScorer:
    """Directional structural fidelity of HTML output vs a reference (0..1).

    Uses rapidfuzz `token_set_ratio` over normalized text, the same directional
    metric the platform's ParseBench v0 scorer uses (a stand-in for the official
    GTRM evaluator). `output.text` is the agent's HTML; `item.expected` is the
    reference HTML. Requires the `parsebench` extra (rapidfuzz).
    """

    threshold: float = 0.8
    name: str = "structural-fidelity"

    def score(self, item: Any, output: FinalOutput, summary: Summary) -> Score:
        from rapidfuzz import fuzz  # provided by the `parsebench` extra

        reference = item.expected if isinstance(item.expected, str) else json.dumps(item.expected)
        got = output.text or ""
        value = fuzz.token_set_ratio(_normalize(reference), _normalize(got)) / 100.0
        passed = value >= self.threshold
        detail = "" if passed else f"fidelity {value:.2f} < threshold {self.threshold}"
        return Score(value=value, passed=passed, detail=detail)
