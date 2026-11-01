"""`--volume HOST:SANDBOX[:ro]`: host paths mounted in the run's sandbox."""

from pathlib import Path, PurePosixPath

from opensandbox.models.sandboxes import Host, Volume

from avp_cli.console import Failed
from avp_cli.sandbox.sandboxes import IO


def parse(volumes: list[str]) -> list[Volume]:
    """Each `--volume`, read-write unless it ends in `:ro`. The host path must
    exist, and the sandbox path must be absolute and outside the run directory's
    `/io`."""
    result = []
    for volume in volumes:
        parts = volume.split(":")
        read_only = parts[-1] == "ro"
        if read_only:
            parts.pop()
        if len(parts) != 2 or not all(parts):
            raise Failed(f"--volume {volume} isn't HOST:SANDBOX or HOST:SANDBOX:ro")
        host = Path(parts[0]).expanduser().resolve()
        path = PurePosixPath(parts[1])
        if not host.exists():
            raise Failed(f"--volume {volume}: {host} doesn't exist")
        if not path.is_absolute():
            raise Failed(f"--volume {volume}: {path} must be an absolute path")
        if path == PurePosixPath(IO) or path.is_relative_to(IO):
            raise Failed(f"--volume {volume}: {IO} is the run directory")
        result.append(
            Volume(
                name=f"volume-{len(result)}",
                host=Host(path=str(host)),
                mount_path=str(path),
                read_only=read_only,
            )
        )
    return result


def describe(volumes: list[Volume]) -> str:
    return ", ".join(
        f"{v.host.path if v.host else v.name} -> {v.mount_path}"
        f"{' (read-only)' if v.read_only else ''}"
        for v in volumes
    )
