"""Derived sandbox images: env spec + agent recipe -> a cached local image.

An environment's `image` + `packages` and the agent's container recipe compile
to a small Dockerfile, content-hashed into a tag (`avp-env:<hash>`). The build
runs once per distinct (env, agent) shape and Docker's layer cache makes
near-misses cheap; every later run reuses the tag instantly. Workspace content
(`paths` / `files`) is deliberately NOT baked in: it seeds a per-run host dir
that's bind-mounted, so editing your project doesn't invalidate the image.

The recipe is the agent's contribution: the RUN steps that install a Linux
build of the agent into the image, and the argv that runs it inside the
sandbox. In-tree agents define theirs in `avp_cli.agents.AGENT_SOURCES`;
third-party manifests carry a `container` block.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from avp_cli.environment import Environment


class ImageBuildError(Exception):
    """`docker build` failed or Docker is missing; message carries the tail."""


@dataclass(frozen=True)
class ContainerRecipe:
    """How an agent gets into, and runs inside, a sandbox image.

    `install`: Dockerfile RUN steps (shell strings) that put a Linux build of
    the agent into the image. They run at build time with network access, so
    release downloads / pip installs happen once per image, not per run.
    `command`: the in-sandbox argv prefix honoring the run contract
    (`<command> run --commission <path> --out <path>`).
    `env`: agent-required sandbox env vars (e.g. claude-code needs
    `IS_SANDBOX=1` to allow bypassPermissions as the container's root user);
    not part of the image, so it doesn't affect the content hash.
    """

    install: tuple[str, ...]
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()


def dockerfile(env: Environment, recipe: ContainerRecipe) -> str:
    """Compile the env's image layers + the agent's install steps to a Dockerfile.

    Layer order is stability-sorted for cache hits: base image, then apt, then
    pip (needs the base to ship pip; the build error says so if not), then the
    agent. `paths`/`files`/`setup` are per-run and never appear here.
    """
    lines = [f"FROM {env.image}"]
    apt = env.packages.get("apt", [])
    if apt:
        lines.append(
            "RUN apt-get update && apt-get install -y --no-install-recommends "
            + " ".join(apt)
            + " && rm -rf /var/lib/apt/lists/*"
        )
    pip = env.packages.get("pip", [])
    if pip:
        lines.append("RUN pip install --no-cache-dir " + " ".join(pip))
    lines.extend(f"RUN {step}" for step in recipe.install)
    return "\n".join(lines) + "\n"


def image_tag(env: Environment, recipe: ContainerRecipe) -> str:
    """Deterministic local tag for this (env, agent) shape."""
    digest = hashlib.sha256(dockerfile(env, recipe).encode()).hexdigest()[:12]
    return f"avp-env:{digest}"


def ensure_image(
    env: Environment,
    recipe: ContainerRecipe,
    *,
    on_line: Callable[[str], None] | None = None,
) -> str:
    """Build (or reuse) the derived image; returns its tag.

    `on_line` receives build output lines for progress display; first builds
    pull the base image and install the agent, so silence would read as a hang.
    """
    docker = shutil.which("docker")
    if docker is None:
        raise ImageBuildError("docker is not on PATH")
    tag = image_tag(env, recipe)
    if subprocess.run([docker, "image", "inspect", tag], capture_output=True).returncode == 0:
        return tag

    df = dockerfile(env, recipe)
    proc = subprocess.Popen(
        [docker, "build", "-t", tag, "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(df)
    proc.stdin.close()
    tail: list[str] = []
    for line in proc.stdout:
        line = line.rstrip()
        tail = [*tail[-19:], line]
        if on_line is not None:
            on_line(line)
    if proc.wait() != 0:
        raise ImageBuildError(
            "docker build failed for the environment image:\n"
            + "\n".join(tail)
            + f"\n\n(Dockerfile)\n{df}"
        )
    return tag
