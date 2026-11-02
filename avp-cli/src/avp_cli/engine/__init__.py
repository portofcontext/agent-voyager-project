"""The container engine, through the Docker API: Docker, or podman through its
Docker socket. Found through `DOCKER_HOST` or the default socket."""

import os

import docker
from docker.errors import DockerException

from avp_cli.console import Failed

DEFAULT_SOCKET = "/var/run/docker.sock"


def where() -> str:
    """Where avp looks for the engine. The default socket is often a link to
    another engine's, such as podman's, so the link's target is shown too."""
    if host := os.environ.get("DOCKER_HOST"):
        return f"{host} (DOCKER_HOST)"
    if not os.path.islink(DEFAULT_SOCKET):
        return DEFAULT_SOCKET
    return f"{DEFAULT_SOCKET} -> {os.readlink(DEFAULT_SOCKET)}"


def client() -> docker.DockerClient:
    try:
        engine = docker.from_env()
        engine.ping()
    except DockerException as exc:
        raise Failed(
            f"no container engine answers at {where()}. Start Docker, or podman with its "
            f"Docker socket, or set DOCKER_HOST. ({exc})"
        ) from None
    return engine


def name() -> str:
    """The engine's name and version, such as `Podman Engine 6.0.1`."""
    version = client().version()
    engine = (version.get("Components") or [{}])[0].get("Name", "")
    if engine in ("", "Engine"):
        # Docker names its component "Engine", and itself in Platform. Podman's
        # Platform is its OS, such as linux/arm64/fedora-44.
        engine = version.get("Platform", {}).get("Name") or "Docker"
    return f"{engine} {version.get('Version', '')} (Docker API {version.get('ApiVersion', '?')})"
