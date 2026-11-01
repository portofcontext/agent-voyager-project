"""The agent command line, run in a sandbox: the image's ENTRYPOINT with
`ping`, `describe`, or `run` after it."""

import json

from opensandbox.sync.sandbox import SandboxSync
from pydantic import ValidationError

from avp.descriptor import AgentDescriptor
from avp_cli.console import Failed
from avp_cli.sandbox import sandboxes

AVP_VERSIONS = ("0.1",)
"""The AVP versions this avp can run agents for."""


def ping(box: SandboxSync, entrypoint: list[str]) -> str:
    """Check the agent runs, and return the AVP version it speaks."""
    output = _call(box, entrypoint, "ping")
    try:
        pong = json.loads(output)
    except json.JSONDecodeError:
        pong = None
    if not isinstance(pong, dict) or pong.get("type") != "pong" or "avp_version" not in pong:
        raise Failed(
            f'`ping` printed {output.strip()!r}, not {{"type": "pong", "avp_version": ...}}'
        )
    version = pong["avp_version"]
    if version not in AVP_VERSIONS:
        raise Failed(f"the agent speaks AVP {version}; this avp supports {', '.join(AVP_VERSIONS)}")
    return version


def describe(box: SandboxSync, entrypoint: list[str]) -> AgentDescriptor:
    output = _call(box, entrypoint, "describe")
    try:
        return AgentDescriptor.model_validate_json(output)
    except ValidationError as exc:
        raise Failed(f"`describe` didn't print an Agent Descriptor: {exc}") from None


def _call(box: SandboxSync, entrypoint: list[str], *args: str) -> str:
    result = sandboxes.run(box, [*entrypoint, *args])
    if result.exit_code != 0:
        raise Failed(
            f"`{' '.join([*entrypoint, *args])}` exited with {result.exit_code}"
            + (f":\n{result.stderr.strip()}" if result.stderr.strip() else "")
        )
    return result.stdout
