from __future__ import annotations

import asyncio

from src.config.schemas import JsonSchemaModel
from src.mcp.client import McpClient
from src.mcp.tools import ClickArgs, TypeArgs


class ActionRequest(JsonSchemaModel):
    action: str
    selector: str | None = None
    value: str | None = None


class ActionResult(JsonSchemaModel):
    ok: bool
    error: str | None = None


class ActionDispatcher:
    def __init__(self, *, mcp_client: McpClient | None = None) -> None:
        self._mcp_client = mcp_client or McpClient()

    async def dispatch(self, request: ActionRequest) -> ActionResult:
        action = request.action.lower()

        if action in {"click", "type", "assert_visible", "assert_text"} and not request.selector:
            return ActionResult(ok=False, error=f"Action '{request.action}' requires a selector")

        if action == "type" and request.value is None:
            return ActionResult(ok=False, error="Action 'type' requires a value")

        if action == "press" and not request.value:
            return ActionResult(ok=False, error="Action 'press' requires a key value")

        if action == "click":
            result = await self._mcp_client.click(ClickArgs(selector=request.selector or ""))
            return ActionResult(ok=result.ok, error=result.error)

        if action == "type":
            result = await self._mcp_client.type_text(
                TypeArgs(selector=request.selector or "", text=request.value or "")
            )
            return ActionResult(ok=result.ok, error=result.error)

        if action == "press":
            result = await self._mcp_client.press_key(key=request.value or "")
            return ActionResult(ok=result.ok, error=result.error)

        if action == "wait":
            wait_seconds = 0.5
            if request.value:
                try:
                    wait_seconds = max(0.0, float(request.value) / 1000.0)
                except ValueError:
                    wait_seconds = 0.5
            await asyncio.sleep(wait_seconds)
            return ActionResult(ok=True, error=None)

        if action == "assert_visible":
            result = await self._mcp_client.call(
                tool_candidates=["browser_is_visible", "is_visible", "query_selector"],
                arguments={"selector": request.selector},
            )
            return ActionResult(ok=result.ok, error=result.error)

        if action == "assert_text":
            result = await self._mcp_client.call(
                tool_candidates=["browser_get_text", "get_text", "query_selector"],
                arguments={"selector": request.selector},
            )
            if not result.ok:
                return ActionResult(ok=False, error=result.error)

            if request.value:
                raw_text = str(result.raw or "")
                if request.value not in raw_text:
                    return ActionResult(ok=False, error=f"Expected text '{request.value}' not found")
            return ActionResult(ok=True, error=None)

        if action not in {"click", "type", "press", "wait", "assert_text", "assert_visible"}:
            return ActionResult(ok=False, error=f"Unsupported action '{request.action}'")

        return ActionResult(ok=True, error=None)
