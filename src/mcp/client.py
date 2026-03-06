from __future__ import annotations

from src.mcp.tools import ClickArgs, NavigateArgs, ToolResult, TypeArgs


class McpClient:
    async def start(self) -> None:
        raise NotImplementedError("MCP start not implemented yet")

    async def stop(self) -> None:
        raise NotImplementedError("MCP stop not implemented yet")

    async def navigate(self, args: NavigateArgs) -> ToolResult:
        raise NotImplementedError("MCP navigate not implemented yet")

    async def click(self, args: ClickArgs) -> ToolResult:
        raise NotImplementedError("MCP click not implemented yet")

    async def type_text(self, args: TypeArgs) -> ToolResult:
        raise NotImplementedError("MCP type_text not implemented yet")
