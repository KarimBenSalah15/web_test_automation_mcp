from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path


class StdioTransport:
    def __init__(self, command: str, args: list[str], cwd: str | None = None) -> None:
        self.command = command
        self.args = args
        self.cwd = cwd
        self._process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            cwd=self.cwd or str(Path.cwd()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def stop(self) -> None:
        if self._process is None:
            return
        process = self._process
        pid = process.pid
        if self._process.stdin is not None:
            self._process.stdin.close()
            with contextlib.suppress(Exception):
                await self._process.stdin.wait_closed()
        if process.returncode is None and os.name == "nt" and pid is not None:
            with contextlib.suppress(Exception):
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/T",
                    "/F",
                    "/PID",
                    str(pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(killer.wait(), timeout=5)
        if process.returncode is None:
            process.terminate()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=5)
            if process.returncode is None:
                process.kill()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=5)
        self._process = None

    async def send(self, payload: dict) -> None:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Transport is not started")
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self._process.stdin.write(data)
        await self._process.stdin.drain()

    async def recv(self) -> dict:
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("Transport is not started")
        line = await self._process.stdout.readline()
        if not line:
            raise RuntimeError("MCP transport closed")
        return json.loads(line.decode("utf-8"))

    async def iter_stderr(self) -> AsyncIterator[str]:
        if self._process is None or self._process.stderr is None:
            return
        while True:
            line = await self._process.stderr.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace").rstrip()
