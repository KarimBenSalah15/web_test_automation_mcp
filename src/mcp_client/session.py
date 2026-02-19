from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

from .jsonrpc import build_request, extract_result, is_notification, is_response
from .transport import StdioTransport


NotificationHandler = Callable[[str, dict[str, Any]], None]


class McpSession:
    def __init__(self, transport: StdioTransport, timeout_seconds: float = 20.0) -> None:
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._notifications: list[NotificationHandler] = []
        self._reader_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.transport.start()
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def stop(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(self._reader_task, timeout=2)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.transport.stop(), timeout=8)

    def on_notification(self, handler: NotificationHandler) -> None:
        self._notifications.append(handler)

    async def initialize(self) -> Any:
        return await self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "clientInfo": {"name": "python-mcp-web-agent", "version": "0.1.0"},
                "capabilities": {},
            },
        )

    async def list_tools(self) -> Any:
        return await self.request("tools/list", {})

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return await self.request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        req = build_request(method, params)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[req.id] = fut
        await self.transport.send(req.to_dict())
        return await asyncio.wait_for(fut, timeout=self.timeout_seconds)

    async def _reader_loop(self) -> None:
        while True:
            message = await self.transport.recv()
            if is_response(message):
                msg_id = int(message["id"])
                future = self._pending.pop(msg_id, None)
                if future is not None and not future.done():
                    try:
                        future.set_result(extract_result(message))
                    except Exception as exc:
                        future.set_exception(exc)
            elif is_notification(message):
                method = message.get("method", "")
                params = message.get("params", {})
                for handler in self._notifications:
                    handler(method, params)
