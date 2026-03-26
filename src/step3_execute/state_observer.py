from __future__ import annotations

import base64
import json
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
        result = await self._mcp_client.call(
            tool_candidates=[
                "list_pages",
                "browser_get_url",
                "get_current_url",
                "get_url",
                "current_url",
                "page_get_url",
            ],
            arguments={},
        )
        text = self._extract_text_content(result.raw if result.ok else None)
        if text:
            url_match = re.search(r"https?://[^\s\"'<>]+", text)
            if url_match:
                return url_match.group(0).rstrip(".,)")
        return "about:blank"

    async def _get_page_title(self) -> str | None:
        """Get the page title from MCP."""
        result = await self._mcp_client.call(
            tool_candidates=[
                "list_pages",
                "browser_get_page_title",
                "get_page_title",
                "page_title",
            ],
            arguments={},
        )
        text = self._extract_text_content(result.raw if result.ok else None)
        if text:
            # Some MCP servers return JSON-like page lists with title fields.
            title_match = re.search(r'"title"\s*:\s*"([^"]+)"', text)
            if title_match:
                return title_match.group(1)
            line = text.splitlines()[0].strip()
            if line and "http" not in line.lower():
                return line
        return None

    async def _get_dom_snapshot(self) -> str | None:
        """Get and clean the DOM snapshot from MCP."""
        result = await self._mcp_client.call(
            tool_candidates=[
                "take_snapshot",
                "browser_get_dom",
                "get_dom",
                "dom_snapshot",
                "get_dom_snapshot",
                "browser_dump_dom",
            ],
            arguments={},
        )
        if not result.ok:
            return None

        dom_html = self._extract_text_content(result.raw)

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
                "list_console_messages",
                "get_console_message",
                "browser_get_console_logs",
                "get_console_logs",
                "console_logs",
                "browser_console",
            ],
            arguments={},
        )
        if not result.ok or not result.raw:
            return None

        logs: list[str] = []
        text = self._extract_text_content(result.raw)
        if text:
            # Parse as JSON array or newline-separated logs
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    logs = [str(entry) for entry in parsed if entry]
            except Exception:
                lines = text.strip().split("\n")
                logs = [line.strip() for line in lines if line.strip()]

        return logs if logs else None

    async def _capture_screenshot(self) -> str | None:
        """Capture and save a screenshot from MCP."""
        result = await self._mcp_client.call(
            tool_candidates=[
                "take_screenshot",
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
            screenshot_data = self._extract_image_base64(result.raw)
            if not screenshot_data:
                screenshot_data = self._extract_text_content(result.raw)

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

    @staticmethod
    def _extract_text_content(raw: dict[str, Any] | None) -> str | None:
        if not raw:
            return None
        content = raw.get("content") or []
        parts: list[str] = []
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                elif isinstance(item, str) and item.strip():
                    parts.append(item.strip())
        return "\n".join(parts).strip() if parts else None

    @staticmethod
    def _extract_image_base64(raw: dict[str, Any] | None) -> str | None:
        if not raw:
            return None
        content = raw.get("content") or []
        if not isinstance(content, list):
            return None

        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "image":
                data = item.get("data")
                if isinstance(data, str) and data.strip():
                    return data.strip()
        return None
