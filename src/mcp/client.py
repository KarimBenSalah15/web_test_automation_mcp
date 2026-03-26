from __future__ import annotations

from contextlib import AsyncExitStack
from datetime import timedelta
import os
from typing import Any
import shlex

try:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except ModuleNotFoundError:  # pragma: no cover - exercised when SDK not installed
    ClientSession = Any  # type: ignore[assignment]
    StdioServerParameters = Any  # type: ignore[assignment]
    stdio_client = None

from src.mcp.tools import ClickArgs, NavigateArgs, ToolResult, TypeArgs


class McpClient:
    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        cwd: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._command = command or os.getenv("MCP_SERVER_COMMAND", "npx")
        self._args = args if args is not None else self._parse_args(os.getenv("MCP_SERVER_ARGS", "-y chrome-devtools-mcp@latest"))
        self._cwd = cwd
        self._timeout = timeout_seconds
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tool_names: set[str] = set()

    async def start(self) -> None:
        if self._session is not None:
            return

        if stdio_client is None:
            raise RuntimeError(
                "The 'mcp' Python package is not installed in this interpreter. "
                "Install dependencies from requirements.txt and retry."
            )

        stack = AsyncExitStack()
        server = StdioServerParameters(
            command=self._command,
            args=self._args,
            cwd=self._cwd,
        )

        read_stream, write_stream = await stack.enter_async_context(stdio_client(server))
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()

        tools = await session.list_tools()
        self._tool_names = {tool.name for tool in tools.tools}
        self._stack = stack
        self._session = session

    async def stop(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None
        self._tool_names = set()

    async def navigate(self, args: NavigateArgs) -> ToolResult:
        tool_name = self._resolve_tool_name(["browser_navigate", "navigate", "page_navigate"])
        return await self._invoke_tool(tool_name=tool_name, arguments={"url": args.url})

    async def click(self, args: ClickArgs) -> ToolResult:
        tool_name = self._resolve_tool_name(["browser_click", "click", "dom_click"])
        return await self._invoke_tool(tool_name=tool_name, arguments={"selector": args.selector})

    async def type_text(self, args: TypeArgs) -> ToolResult:
        tool_name = self._resolve_tool_name(["browser_type", "type", "fill", "input_text"])
        primary = await self._invoke_tool(
            tool_name=tool_name,
            arguments={"selector": args.selector, "text": args.text},
        )
        if primary.ok:
            return primary

        # Some servers use "value" instead of "text".
        return await self._invoke_tool(
            tool_name=tool_name,
            arguments={"selector": args.selector, "value": args.text},
        )

    async def press_key(self, *, key: str) -> ToolResult:
        tool_name = self._resolve_tool_name(["browser_press_key", "press_key", "keyboard_press"])
        return await self._invoke_tool(tool_name=tool_name, arguments={"key": key})

    async def call(self, *, tool_candidates: list[str], arguments: dict[str, Any]) -> ToolResult:
        try:
            tool_name = self._resolve_tool_name(tool_candidates)
        except Exception as exc:
            return ToolResult(ok=False, error=str(exc), raw=None)
        return await self._invoke_tool(tool_name=tool_name, arguments=arguments)

    def _resolve_tool_name(self, candidates: list[str]) -> str:
        lowered = {name.lower(): name for name in self._tool_names}
        for candidate in candidates:
            match = lowered.get(candidate.lower())
            if match is not None:
                return match
        raise RuntimeError(
            f"None of the tool candidates were found: {', '.join(candidates)}. "
            f"Available tools: {', '.join(sorted(self._tool_names))}"
        )

    async def _invoke_tool(self, *, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            await self.start()
            assert self._session is not None
            result = await self._session.call_tool(
                name=tool_name,
                arguments=arguments,
                read_timeout_seconds=timedelta(seconds=self._timeout),
            )
            raw = result.model_dump(mode="json")
            if result.isError:
                return ToolResult(ok=False, error=self._extract_error_text(raw), raw=raw)
            return ToolResult(ok=True, error=None, raw=raw)
        except Exception as exc:
            return ToolResult(ok=False, error=f"MCP call failed for '{tool_name}': {exc}", raw=None)

    @staticmethod
    def _extract_error_text(raw: dict[str, Any]) -> str:
        content = raw.get("content") or []
        text_parts: list[str] = []
        for part in content:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
        return " | ".join(text_parts) if text_parts else "MCP tool returned an error"

    @staticmethod
    def _parse_args(raw_args: str) -> list[str]:
        return shlex.split(raw_args)
