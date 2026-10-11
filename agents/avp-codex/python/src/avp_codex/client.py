"""Small stdio JSON-RPC client for the native Codex app-server."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from typing import Any


class AppServer:
    def __init__(self, home: str, cwd: str, config: dict[str, Any]):
        self.home, self.cwd, self.config = home, cwd, config
        self.pending: dict[int, asyncio.Future] = {}
        self.events: asyncio.Queue = asyncio.Queue()
        self.sequence = 0

    async def __aenter__(self):
        args = ["codex", "app-server"]
        for key, value in self.config.items():
            args.extend(["-c", f"{key}={toml(value)}"])
        self.process = await asyncio.create_subprocess_exec(
            *args,
            cwd=self.cwd,
            env={**os.environ, "CODEX_HOME": self.home},
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            # Native diagnostics can contain credentials or model content. Errors
            # reach the trajectory through the structured protocol instead.
            stderr=asyncio.subprocess.DEVNULL,
            limit=16 * 1024 * 1024,
        )
        self.reader = asyncio.create_task(self._read())
        return self

    async def __aexit__(self, *args):
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.reader

    async def send(self, message: dict):
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        await self.process.stdin.drain()

    async def request(self, method: str, params: dict):
        self.sequence += 1
        ident = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[ident] = future
        try:
            await self.send({"id": ident, "method": method, "params": params})
            return await asyncio.wait_for(future, 120)
        finally:
            self.pending.pop(ident, None)

    async def _read(self):
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if "method" in message:
                    if "id" in message:
                        # AVP has no mid-run supervisor callback. Never invent
                        # answers to interactive tool/approval requests.
                        await self.send(
                            {
                                "id": message["id"],
                                "error": {
                                    "code": -32601,
                                    "message": "AVP runs cannot request user input",
                                },
                            }
                        )
                    else:
                        await self.events.put(message)
                elif (
                    future := self.pending.get(message.get("id"))
                ) is not None and not future.done():
                    if "error" in message:
                        future.set_exception(RuntimeError(str(message["error"])))
                    else:
                        future.set_result(message["result"])
            raise RuntimeError("Codex app-server closed its event stream")
        except Exception as exc:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(exc)
            await self.events.put(exc)

    async def notification(self):
        message = await self.events.get()
        if isinstance(message, Exception):
            raise message
        return message


def toml(value: Any) -> str:
    """Encode the JSON-valued config subset accepted by Codex's -c option."""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(k)} = {toml(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(toml(v) for v in value) + "]"
    if value is None:
        raise ValueError("TOML config cannot contain null")
    return json.dumps(value)
