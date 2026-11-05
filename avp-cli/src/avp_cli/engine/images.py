"""Agent images: build one from a Dockerfile or pull a published one, read its
entrypoint, remove it."""

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


def pull(reference: str, tag: str, progress: Callable[[int], None] | None = None) -> str:
    """Pull the image at `reference`, which names a digest, and name it `tag`. `progress` is called with the bytes downloaded so far. Returns the
    engine's name for the image, as `build` does."""
    engine = client()
    layers: dict[str, int] = {}
    # Pulled with its tag, some engines keep that tag as a name of the image.
    repository, _, digest = reference.partition("@")
    if ":" in repository.rsplit("/", 1)[-1]:
        repository = repository.rsplit(":", 1)[0]
    pinned = f"{repository}@{digest}"
    try:
        for chunk in engine.api.pull(pinned, stream=True, decode=True):
            if "error" in chunk:
                raise Failed(f"couldn't pull {reference}: {chunk['error'].strip()}")
            status, layer = chunk.get("status", ""), chunk.get("id")
            if status:
                detail(f"{layer}: {status}" if layer else status)
            current = (chunk.get("progressDetail") or {}).get("current")
            if layer and status == "Downloading" and current:
                layers[layer] = current
                if progress:
                    progress(sum(layers.values()))
        engine.images.get(pinned).tag(tag)
    except APIError as exc:
        raise Failed(f"couldn't pull {reference}: {exc.explanation or exc}") from None
    # The image can have other names already, when its content was here before.
    return next(name for name in engine.images.get(tag).tags if name.startswith(tag))


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


def image_id(image: str) -> str:
    """The engine's ID for the image, which changes when it's rebuilt."""
    return client().images.get(image).id


def remove(image: str) -> None:
    """Remove the image's name, and the image when no tag names it any longer.
    A pulled image otherwise stays, held by the digest it was pulled at."""
    engine = client()
    try:
        found = engine.images.get(image).id
        engine.images.remove(image)
        # Some engines list a digest reference among the tags.
        if not [name for name in engine.images.get(found).tags if "@" not in name]:
            engine.images.remove(found, force=True)
    except NotFound:
        # Docker raises ImageNotFound, a NotFound; podman a plain NotFound.
        pass
    except APIError as exc:
        if exc.status_code != 409:
            raise
        raise Failed(f"{image} is in use by a container; stop it, then retry") from None
