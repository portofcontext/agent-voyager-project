"""Environment discovery for avp-openai-agent.

Cheap reads to answer "what does this machine look like to the OpenAI
Agents SDK before we open a run?" Used by supervisors that want to gate
test runs / examples on preflight (e.g., skip an example with exit 2
when no API key is set).
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Environment:
    """Preflight snapshot for the OpenAI Agents SDK runtime.

    `has_sdk`: `openai-agents` (import `agents`) is importable.
    `has_api_key`: `OPENAI_API_KEY` is set (any value).
    `provider`: which API the SDK will hit — `openai`, `azure.openai`,
        or `openai-compatible` (when `OPENAI_BASE_URL` points elsewhere).
    `base_url`: the configured base URL, if any. None if the SDK will
        use its default.
    """

    has_sdk: bool
    has_api_key: bool
    provider: str
    base_url: str | None


def discover_environment() -> Environment:
    has_sdk = importlib.util.find_spec("agents") is not None
    has_api_key = bool(os.environ.get("OPENAI_API_KEY"))
    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE")
    bu_lower = (base_url or "").lower()
    if not bu_lower or "api.openai.com" in bu_lower:
        provider = "openai"
    elif "openai.azure.com" in bu_lower or "azure" in bu_lower:
        provider = "azure.openai"
    else:
        provider = "openai-compatible"
    return Environment(
        has_sdk=has_sdk,
        has_api_key=has_api_key,
        provider=provider,
        base_url=base_url,
    )


__all__ = ["Environment", "discover_environment"]
