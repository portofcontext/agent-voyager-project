"""The mock model that cases script their responses in: aimock, from its
published image, in a sandbox of its own with no outbound access. aimock takes
one format for a response and answers in the format of each provider's API. With
`--strict`, a request no case scripted gets an error, not an invented reply."""

import json
import shlex
import time
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Protocol

from opensandbox.exceptions import SandboxException
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.filesystem import WriteEntry
from opensandbox.sync.sandbox import SandboxSync

from avp_cli.conformance.cases import Response
from avp_cli.console import Failed, err, line
from avp_cli.sandbox import sandboxes

IMAGE = (
    "ghcr.io/copilotkit/aimock:1.47.0"
    "@sha256:3a7d95b3a2ffbe5da70e72d77b26451c4b2ac317706bc55daa7e7ea667ce97eb"
)
"""To upgrade aimock, change this. `--mock-image` runs another for one check."""
PORT = 4010
FIXTURES = "/tmp/avp-fixtures.json"
LOG = "/tmp/avp-aimock.log"
LIFETIME = timedelta(hours=6)
"""Longer than any check. The sandbox is deleted when the check ends, so this
only stops a sandbox's usual lifetime from ending the mock mid-check."""
START_TIMEOUT_S = 15

PATHS = {"anthropic": "", "google": "", "openai": "/v1"}
"""What each provider's `model.base_url` adds to the mock's address. aimock
serves a provider's API at that API's own path, and each SDK adds part of it to
`base_url`: all of it for Anthropic and Google, all but `/v1` for OpenAI."""

_ROUTES = f"http://127.0.0.1:{PORT}/__aimock/routes"
_READY = f"fetch('{_ROUTES}').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
_ADDRESS = (
    "console.log(Object.values(require('os').networkInterfaces()).flat()"
    ".find(a=>a.family==='IPv4'&&!a.internal)?.address??'')"
)


class Scripted(Protocol):
    """A prompt and the model's responses to it, in order. A conformance case
    is one."""

    @property
    def prompt(self) -> str: ...
    @property
    def responses(self) -> Sequence[Response]: ...


def path(provider: str) -> str:
    """What `model.base_url` adds to the mock's address for `provider`."""
    if provider not in PATHS:
        raise Failed(
            f"the mock model can't serve {provider!r} yet; --model can name a model from "
            + ", ".join(sorted(PATHS))
        )
    return PATHS[provider]


def fixtures(cases: Iterable[Scripted]) -> dict[str, Any]:
    """aimock's fixture file: each case's responses in order, matched on the
    case's prompt and how many responses came before. Both come from the
    request, so runs at the same time can share a mock."""
    return {
        "fixtures": [
            {"match": {"userMessage": case.prompt, "turnIndex": turn}, "response": response}
            for case in cases
            for turn, response in enumerate(case.responses)
        ]
    }


@contextmanager
def serving(cases: Iterable[Scripted], image: str = IMAGE) -> Generator[str]:
    """A running mock with the cases' responses, deleted on exit. Yields the
    address an agent's sandbox reaches it at, when allowed that host."""
    with (
        err.status(line("Starting the mock model")) as status,
        sandboxes.sandbox(image, allowed_hosts=[], lifetime=LIFETIME) as box,
    ):
        try:
            address = _start(box, fixtures(cases), image)
        except SandboxException as exc:
            raise Failed(f"the mock model from {image} didn't start: {exc}") from None
        status.stop()
        yield f"http://{address}:{PORT}"


def _start(box: SandboxSync, scripted: dict[str, Any], image: str) -> str:
    box.files.write_files([WriteEntry(path=FIXTURES, data=json.dumps(scripted), mode=644)])
    command = shlex.join(
        [
            "node",
            "/app/dist/cli.js",
            "--fixtures",
            FIXTURES,
            "--host",
            "0.0.0.0",
            "--port",
            str(PORT),
            "--strict",
            "--validate-on-load",
        ]
    )
    box.commands.run(f"{command} > {LOG} 2>&1", opts=RunCommandOpts(background=True))
    deadline = time.monotonic() + START_TIMEOUT_S
    while sandboxes.run(box, ["node", "-e", _READY]).exit_code != 0:
        if time.monotonic() > deadline:
            log = sandboxes.run(box, ["cat", LOG]).stdout.strip()
            raise Failed(f"the mock model from {image} didn't start. Its log:\n{log}")
        time.sleep(0.2)
    address = sandboxes.run(box, ["node", "-e", _ADDRESS]).stdout.strip()
    if not address:
        raise Failed(f"the mock model from {image} has no address another sandbox can reach")
    return address
