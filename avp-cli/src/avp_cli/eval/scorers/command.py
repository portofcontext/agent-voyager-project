"""`command`: a command of the user's, run on the host for each run."""

import asyncio
import shlex
from pathlib import Path
from typing import Annotated

from pydantic import Field, ValidationError

from avp_cli.eval.schemas import JsonObject
from avp_cli.eval.scoring import Run, Score, Scorer, ScorerConfig, ScorerError, ScorerInput


class Command(ScorerConfig):
    """A command of the user's, run on the host for each run: the input goes
    to its stdin as JSON, and it prints the score to stdout as JSON. It runs
    in the eval file's directory with the user's environment."""

    name = "command"

    command: Annotated[list[str], Field(min_length=1)]
    """The program and its arguments. A relative program path is relative to
    the eval file's directory."""
    config: JsonObject = {}
    """Passed to the command as the input's `config`."""

    @classmethod
    def scorer(cls, base: Path) -> Scorer:
        async def score(input: ScorerInput) -> Score:
            return await cls.model_validate(input.config).run(input.run, base)

        return score

    async def run(self, run: Run, base: Path) -> Score:
        shown = shlex.join(self.command)
        stdin = ScorerInput(run=run, config=self.config).model_dump_json()
        try:
            process = await asyncio.create_subprocess_exec(
                *self.command,
                cwd=base,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            raise ScorerError(f"can't run {shown}: {error.strerror or error}") from error
        out, err = await process.communicate(stdin.encode())
        stdout, stderr = out.decode(errors="replace"), err.decode(errors="replace")
        if process.returncode != 0:
            raise ScorerError(
                f"{shown} exited with {process.returncode}{_last_line(stderr)}", stderr
            )
        try:
            return Score.model_validate_json(stdout)
        except ValidationError as error:
            first = error.errors()[0]
            where = ".".join(map(str, first["loc"]))
            problem = f"{where}: {first['msg']}" if where else first["msg"]
            raise ScorerError(
                f"{shown} printed something other than a score: {problem}",
                f"stdout:\n{stdout}\nstderr:\n{stderr}",
            ) from None


def _last_line(stderr: str) -> str:
    lines = stderr.strip().splitlines()
    return f": {lines[-1]}" if lines else ""
