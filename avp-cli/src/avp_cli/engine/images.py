"""Agent images: build one from a Dockerfile, read its entrypoint, remove it."""

from pathlib import Path

from docker.errors import APIError, ImageNotFound

from avp_cli.console import Failed, err
from avp_cli.engine import client

SHELLS = (["/bin/sh", "-c"], ["sh", "-c"])


def build(dockerfile: Path, context: Path, tag: str) -> str:
    """Build the image, printing the build's output as it arrives. Returns the
    engine's name for it, such as podman's `localhost/avp/pd:latest`."""
    engine = client()
    for chunk in engine.api.build(
        path=str(context), dockerfile=str(dockerfile.resolve()), tag=tag, rm=True, decode=True
    ):
        if "error" in chunk:
            raise Failed(
                f"the image build failed: {chunk['error'].strip()}\n"
                f"The build context was {context.resolve()}; --context sets another."
            )
        if text := chunk.get("stream", "").rstrip():
            err.print(text, style="dim", markup=False, highlight=False)
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
    except ImageNotFound:
        pass
    except APIError as exc:
        if exc.status_code != 409:
            raise
        raise Failed(f"{image} is in use by a container; stop it, then retry") from None
