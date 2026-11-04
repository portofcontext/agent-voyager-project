"""`match`: the run's text output compared with an expected string."""

import re
from typing import Annotated, Literal

from pydantic import Field, model_validator
from rapidfuzz.distance import Levenshtein

from avp_cli.eval.scoring import Run, Score, ScorerConfig


def _fold(text: str, case_sensitive: bool) -> str:
    text = text.strip()
    return text if case_sensitive else text.casefold()


def _strings_match(output: str, expected: str, case_sensitive: bool = False) -> bool:
    """Equal after trimming whitespace, and ignoring case unless
    `case_sensitive`. A future `structured-match` compares strings with it."""
    return _fold(output, case_sensitive) == _fold(expected, case_sensitive)


def similarity(output: str, expected: str, case_sensitive: bool = False) -> float:
    """1 minus the Levenshtein distance over the longer string's length, after
    trimming and, unless `case_sensitive`, ignoring case. Two empty strings
    are 1."""
    a, b = _fold(output, case_sensitive), _fold(expected, case_sensitive)
    return Levenshtein.normalized_similarity(a, b)


def _failed(reason: str, value: float = 0) -> Score:
    return Score(value=value, passed=False, reasons=[reason])


def _not(kind: str, run: Run) -> Score:
    """The score of an output that isn't the kind the scorer compares."""
    why = f"reason: {run.reason}" if run.reason else "no agent_stopped"
    return Score(value=0, passed=False, reasons=[f"output isn't {kind} ({why})"])


class Match(ScorerConfig):
    """The run's output, a string, compared with `expected` by `mode`. avp
    never parses the output as JSON."""

    name = "match"

    expected: str
    """The text the output should be, or with `regex` a pattern it should
    contain. Usually a placeholder, such as `{item.answer}`."""
    mode: Literal["exact", "levenshtein", "regex"] = "exact"
    """`exact`: equal. `levenshtein`: similar enough, by Levenshtein distance,
    with partial credit. `regex`: `expected` is found in the output."""
    case_sensitive: bool = False
    threshold: Annotated[float, Field(ge=0, le=1)] | None = None
    """The similarity a run needs to pass. Required with `levenshtein`, and
    only allowed with it."""

    @model_validator(mode="after")
    def _fields_for_mode(self) -> "Match":
        if self.mode == "levenshtein" and self.threshold is None:
            raise ValueError("threshold is required with mode levenshtein")
        if self.mode != "levenshtein" and self.threshold is not None:
            raise ValueError(f"threshold only applies to mode levenshtein, not {self.mode}")
        if self.mode == "regex":
            try:
                re.compile(self.expected)
            except re.error as error:
                raise ValueError(f"expected isn't a valid regular expression: {error}") from None
        return self

    def score(self, run: Run) -> Score:
        if not isinstance(run.output, str):
            return _not("a string", run)
        output = run.output.strip()
        match self.mode:
            case "exact":
                if _strings_match(output, self.expected, self.case_sensitive):
                    return Score(value=1, passed=True)
                return _failed(f"expected {self.expected!r}, got {run.output!r}")
            case "levenshtein":
                assert self.threshold is not None
                value = similarity(output, self.expected, self.case_sensitive)
                if value >= self.threshold:
                    return Score(value=value, passed=True)
                return _failed(
                    f"expected {self.expected!r}, got {run.output!r}: similarity"
                    f" {value:.2f}, below {self.threshold}",
                    value,
                )
            case "regex":
                flags = 0 if self.case_sensitive else re.IGNORECASE
                if re.search(self.expected, output, flags):
                    return Score(value=1, passed=True)
                return _failed(f"no match for {self.expected!r} in {run.output!r}")
