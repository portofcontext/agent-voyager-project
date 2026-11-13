"""Built-in agents: a published image pinned by digest, or the packaged
Dockerfile and a pinned, verified source archive to build one from."""

import hashlib
import json
import posixpath
import shutil
import tarfile
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx

from avp_cli.console import Failed, detail

PACKAGE = Path(__file__).parent
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class Agent:
    agent_name: str
    version: str
    directory: str
    image: str | None = None
    """The published image, pinned by digest. None when this agent's version
    has no published image, so it installs by building from the source."""


@dataclass(frozen=True)
class Catalog:
    commit: str
    sha256: str
    agents: dict[str, Agent]


def catalog() -> Catalog:
    data = json.loads((PACKAGE / "builtins.json").read_text())
    return Catalog(
        commit=data["commit"],
        sha256=data["sha256"],
        agents={name: Agent(**agent) for name, agent in data["agents"].items()},
    )


def get(name: str) -> Agent:
    agents = catalog().agents
    if name not in agents:
        raise Failed(
            f"{name!r} is not a built-in agent. Built-in names: {', '.join(agents)}. "
            "For a custom agent, provide its Dockerfile."
        )
    return agents[name]


@contextmanager
def context(name: str) -> Generator[Path]:
    """Download the pinned source and yield only this agent's build context."""
    agent = get(name)
    source = catalog()
    url = "https://codeload.github.com/portofcontext/agent-voyager-project/tar.gz/" + source.commit
    detail(f"Source: {source.commit}, {agent.directory}")
    with tempfile.TemporaryDirectory(prefix="avp-agent-") as temporary:
        directory = Path(temporary)
        archive = directory / "source.tar.gz"
        digest = hashlib.sha256()
        size = 0
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                with archive.open("wb") as output:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_ARCHIVE_BYTES:
                            raise Failed("the agent source archive exceeds 50 MiB")
                        digest.update(chunk)
                        output.write(chunk)
        except httpx.HTTPError as exc:
            raise Failed(f"couldn't download the agent source: {exc}") from None
        if digest.hexdigest() != source.sha256:
            raise Failed("the agent source archive's SHA-256 does not match the CLI's pin")
        build = directory / "build"
        build.mkdir()
        prefix = f"agent-voyager-project-{source.commit}/{agent.directory}"
        _extract(archive, prefix, build / agent.directory)
        root = f"agent-voyager-project-{source.commit}"
        language = agent.directory.rsplit("/", 1)[-1]
        sdk = f"avp-sdk/{language}"
        links = {
            f"src/{'avp/' if language == 'python' else ''}utils/data/{name}": f"{root}/avp-sdk/data/{name}"
            for name in ("avp_endpoint_defaults.json", "avp_endpoints.json", "avp_prices.json")
        }
        if language == "typescript":
            links["src/schemas/trajectory.json"] = f"{root}/spec/v0.1/trajectory.schema.json"
            links["src/schemas/artifacts.json"] = f"{root}/spec/v0.1/artifacts.schema.json"
        _extract(archive, f"{root}/{sdk}", build / sdk, links=links)
        _extract(archive, f"{root}/avp-sdk/data", build / "avp-sdk/data")
        _extract(archive, f"{root}/spec/v0.1", build / "spec/v0.1")
        shutil.copyfile(PACKAGE / "dockerfiles" / f"{name}.Dockerfile", build / "Dockerfile")
        yield build


def _extract(
    archive: Path, prefix: str, destination: Path, *, links: dict[str, str] | None = None
) -> None:
    """Copy regular files only, without following archive links or parent paths."""
    count = 0
    with tarfile.open(archive) as source:
        for member in source:
            path = PurePosixPath(member.name)
            if not path.is_relative_to(prefix):
                continue
            relative = path.relative_to(prefix)
            if ".." in relative.parts:
                raise Failed("the agent source archive contains an unsafe path")
            target = destination.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise Failed("the agent source archive contains an unsafe path")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if member.issym() and links and relative.as_posix() in links:
                expected = links[relative.as_posix()]
                actual = posixpath.normpath(posixpath.join(str(path.parent), member.linkname))
                if actual != expected:
                    raise Failed("the SDK source contains an unexpected data link")
                member = source.getmember(expected)
            if not member.isfile():
                raise Failed("the agent source archive contains a link or special file")
            target.parent.mkdir(parents=True, exist_ok=True)
            content = source.extractfile(member)
            assert content is not None
            with content, target.open("wb") as output:
                shutil.copyfileobj(content, output)
            target.chmod(member.mode & 0o777)
            count += 1
    if not count:
        raise Failed("the agent source archive does not contain the pinned agent directory")
