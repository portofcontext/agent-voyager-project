"""Agent images: build one from a Dockerfile, read its entrypoint, remove it."""

import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from docker.errors import APIError, NotFound

from avp_cli.console import Failed, detail
from avp_cli.engine import client

SHELLS = (["/bin/sh", "-c"], ["sh", "-c"])
BUILD_TAIL = 20
"""Build output lines a failed build shows without --verbose."""
STEP = re.compile(r"(?:STEP|Step) (\d+/\d+) ?: ?(.*)")
"""A build step's first line: podman's `STEP 3/7: RUN ...`, Docker's `Step 3/7 : RUN ...`."""


@dataclass(frozen=True)
class Step:
    number: str
    """Such as `3/7`."""
    instruction: str
    """The instruction's first line, such as `RUN uv sync`."""
    cached: bool = False


def build(
    dockerfile: Path, context: Path, tag: str, step: Callable[[Step], None] | None = None
) -> str:
    """Build the image. `step` is called with each step as it starts, and
    again with `cached` set when the engine reuses it. The build's output prints as it arrives with --verbose, and its end
    with a failure. Returns the engine's name for the image, such as podman's
    `localhost/avp/pd:latest`."""
    engine = client()
    tail: deque[str] = deque(maxlen=BUILD_TAIL)
    current: Step | None = None
    for chunk in engine.api.build(
        path=str(context),
        dockerfile=str(dockerfile.resolve()),
        tag=tag,
        rm=True,
        forcerm=True,
        decode=True,
    ):
        if "error" in chunk:
            output = "".join(f"\n  {line}" for line in tail)
            raise Failed(
                f"the image build failed: {chunk['error'].strip()}\n"
                f"The build context was {context.resolve()}; --context sets another."
                + (f"\nThe build's output ends:{output}" if output else "")
            )
        if text := chunk.get("stream", "").rstrip():
            tail.extend(text.splitlines())
            detail(text)
            if step is None:
                continue
            for line in text.splitlines():
                if match := STEP.match(line):
                    current = Step(match[1], match[2])
                    step(current)
                elif current and "Using cache" in line:
                    step(Step(current.number, current.instruction, cached=True))
    return engine.images.get(tag).tags[0]


def entrypoint(image: str) -> list[str]:
    """The image's ENTRYPOINT: the agent's command line, which avp runs with
    `ping`, `describe`, or `run` after it."""
    command = client().images.get(image).attrs["Config"].get("Entrypoint")
    if not command:
        raise Failed(
            'the image has no ENTRYPOINT. Set it to the agent\'s command line: ENTRYPOINT ["my-agent-cli"]'
        )
    if command[:2] in SHELLS:
        raise Failed(
            "the image's ENTRYPOINT is in shell form, which drops the arguments avp adds. "
            'Use the exec form: ENTRYPOINT ["my-agent-cli"]'
        )
    return command


def remove(image: str) -> None:
    try:
        client().images.remove(image)
    except NotFound:
        # Docker raises ImageNotFound, a NotFound; podman a plain NotFound.
        pass
    except APIError as exc:
        if exc.status_code != 409:
            raise
        raise Failed(f"{image} is in use by a container; stop it, then retry") from None
