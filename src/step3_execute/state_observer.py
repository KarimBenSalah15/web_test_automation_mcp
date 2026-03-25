from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any

from src.config.schemas import JsonSchemaModel
from src.mcp.client import McpClient


class PageStateSnapshot(JsonSchemaModel):
    url: str
    title: str | None = None
    dom_excerpt: str | None = None
    console_logs: list[str] | None = None
    screenshot_path: str | None = None


class StateObserver:
    def __init__(self, mcp_client: McpClient) -> None:
        self._mcp_client = mcp_client
        self._artifacts_dir = "artifacts"
        Path(self._artifacts_dir).mkdir(exist_ok=True)

    async def snapshot(self) -> PageStateSnapshot:
        """Capture the real page state via MCP."""
        url = await self._get_current_url()
        title = await self._get_page_title()
        dom_excerpt = await self._get_dom_snapshot()
        console_logs = await self._get_console_logs()
        screenshot_path = await self._capture_screenshot()

        return PageStateSnapshot(
            url=url,
            title=title,
            dom_excerpt=dom_excerpt,
            console_logs=console_logs,
            screenshot_path=screenshot_path,
        )

    async def _get_current_url(self) -> str:
        """Get the current page URL from MCP."""
        # Try multiple candidate tool names that different MCP servers might use
        result = await self._mcp_client.call(
            tool_candidates=[
                "browser_get_url",
                "get_current_url",
                "get_url",
                "current_url",
                "page_get_url",
            ],
            arguments={},
        )
        if result.ok and result.raw:
            # Extract URL from response (handle both string and dict formats)
            content = result.raw.get("content", [])
            if isinstance(content, list) and content:
                text = content[0].get("text") if isinstance(content[0], dict) else str(content[0])
                if text and text.strip():
                    return text.strip()
        return "about:blank"

    async def _get_page_title(self) -> str | None:
        """Get the page title from MCP."""
        result = await self._mcp_client.call(
            tool_candidates=[
                "browser_get_page_title",
                "get_page_title",
                "page_title",
            ],
            arguments={},
        )
        if result.ok and result.raw:
            content = result.raw.get("content", [])
            if isinstance(content, list) and content:
                text = content[0].get("text") if isinstance(content[0], dict) else str(content[0])
                if text and text.strip():
                    return text.strip()
        return None

    async def _get_dom_snapshot(self) -> str | None:
        """Get and clean the DOM snapshot from MCP."""
        result = await self._mcp_client.call(
            tool_candidates=[
                "browser_get_dom",
                "get_dom",
                "dom_snapshot",
                "get_dom_snapshot",
                "browser_dump_dom",
            ],
            arguments={},
        )
        if not result.ok or not result.raw:
            return None

        # Extract DOM content from response
        content = result.raw.get("content", [])
        dom_html = ""
        if isinstance(content, list) and content:
            text = content[0].get("text") if isinstance(content[0], dict) else str(content[0])
            if text and text.strip():
                dom_html = text.strip()

        if not dom_html:
            return None

        # Clean and truncate the DOM for LLM consumption
        cleaned = self._clean_dom(dom_html)
        # Truncate to 8000 chars to avoid overwhelming the LLM
        if len(cleaned) > 8000:
            cleaned = cleaned[:8000] + "\n... (truncated)"
        return cleaned

    async def _get_console_logs(self) -> list[str] | None:
        """Get console logs (errors/warnings) from MCP."""
        result = await self._mcp_client.call(
            tool_candidates=[
                "browser_get_console_logs",
                "get_console_logs",
                "console_logs",
                "browser_console",
            ],
            arguments={},
        )
        if not result.ok or not result.raw:
            return None

        content = result.raw.get("content", [])
        logs: list[str] = []
        if isinstance(content, list) and content:
            text = content[0].get("text") if isinstance(content[0], dict) else str(content[0])
            if text and text.strip():
                # Parse as JSON array or newline-separated logs
                try:
                    import json
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        logs = [str(entry) for entry in parsed if entry]
                except Exception:
                    # If not JSON, treat as plain text
                    lines = text.strip().split("\n")
                    logs = [line.strip() for line in lines if line.strip()]

        return logs if logs else None

    async def _capture_screenshot(self) -> str | None:
        """Capture and save a screenshot from MCP."""
        result = await self._mcp_client.call(
            tool_candidates=[
                "browser_screenshot",
                "screenshot",
                "capture_screenshot",
                "browser_capture_screenshot",
            ],
            arguments={},
        )
        if not result.ok or not result.raw:
            return None

        try:
            content = result.raw.get("content", [])
            screenshot_data = None
            if isinstance(content, list) and content:
                # Check for base64 encoded image
                text = content[0].get("text") if isinstance(content[0], dict) else str(content[0])
                if text and text.strip():
                    screenshot_data = text.strip()

            if screenshot_data:
                # Save as PNG in artifacts folder
                import datetime as dt
                timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_filename = f"screenshot_{timestamp}.png"
                screenshot_path = os.path.join(self._artifacts_dir, screenshot_filename)

                # Decode base64 if necessary
                if screenshot_data.startswith("data:image"):
                    # Data URI format
                    screenshot_data = screenshot_data.split(",", 1)[1]
                
                with open(screenshot_path, "wb") as f:
                    f.write(base64.b64decode(screenshot_data))
                return screenshot_path
        except Exception:
            # Screenshot capture failed, but that's optional
            pass

        return None

    @staticmethod
    def _clean_dom(html: str) -> str:
        """Clean DOM HTML for LLM consumption."""
        # Remove script and style tags entirely
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove elements with the hidden attribute - match by capturing the tag name
        # This ensures we match the correct closing tag
        def remove_hidden_elements(text: str) -> str:
            pattern = r'<(\w+)(?:\s+[^>]*)?\s+hidden(?:\s[^>]*)?>.*?</\1>'
            return re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)
        
        html = remove_hidden_elements(html)

        # Remove style and data attributes but keep class and aria-label for context
        html = re.sub(r'\s*style\s*=\s*["\'][^"\']*["\']', "", html, flags=re.IGNORECASE)
        html = re.sub(r'\s*data-[a-z-]*\s*=\s*["\'][^"\']*["\']', "", html, flags=re.IGNORECASE)
        html = re.sub(r'\s*aria-(?!label)[a-z-]*\s*=\s*["\'][^"\']*["\']', "", html, flags=re.IGNORECASE)

        # Normalize whitespace
        html = re.sub(r"\s+", " ", html)
        html = re.sub(r">\s+<", "><", html)

        return html.strip()
