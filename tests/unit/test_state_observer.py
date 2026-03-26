"""Unit tests for StateObserver with mocked MCP client."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.mcp.tools import ToolResult
from src.step3_execute.state_observer import StateObserver, PageStateSnapshot


def _has_candidate(tool_candidates: list[str], *needles: str) -> bool:
    lowered = [candidate.lower() for candidate in tool_candidates]
    return any(any(needle in candidate for needle in needles) for candidate in lowered)


@pytest.mark.asyncio
async def test_state_observer_captures_real_page_state() -> None:
    """Test that StateObserver correctly captures page state from MCP."""
    mock_mcp = AsyncMock()
    mock_mcp.call = AsyncMock()
    
    # Mock responses for each tool call
    async def mock_call(*, tool_candidates: list[str], arguments: dict) -> ToolResult:
        # Determine which tool is being called based on candidates
        if _has_candidate(tool_candidates, "title"):
            return ToolResult(
                ok=True,
                error=None,
                raw={"content": [{"text": "Example Search Page"}]},
            )
        elif _has_candidate(tool_candidates, "list_pages", "url"):
            return ToolResult(
                ok=True,
                error=None,
                raw={"content": [{"text": "https://example.com/search"}]},
            )
        elif _has_candidate(tool_candidates, "snapshot", "dom"):
            return ToolResult(
                ok=True,
                error=None,
                raw={
                    "content": [
                        {
                            "text": """
                            <html>
                                <head><title>Example</title></head>
                                <body>
                                    <input id="q" placeholder="Search..." />
                                    <button>Search</button>
                                    <div hidden>Hidden content</div>
                                    <script>console.log("test");</script>
                                </body>
                            </html>
                            """
                        }
                    ]
                },
            )
        elif _has_candidate(tool_candidates, "console"):
            return ToolResult(
                ok=True,
                error=None,
                raw={"content": [{"text": '["Warning: deprecated API"]'}]},
            )
        elif _has_candidate(tool_candidates, "screenshot"):
            return ToolResult(
                ok=True,
                error=None,
                raw={"content": [{"text": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}]},
            )
        return ToolResult(ok=False, error="Unknown tool", raw=None)
    
    mock_mcp.call = mock_call
    
    observer = StateObserver(mcp_client=mock_mcp)
    snapshot = await observer.snapshot()
    
    # Verify snapshot structure
    assert isinstance(snapshot, PageStateSnapshot)
    assert snapshot.url == "https://example.com/search"
    assert snapshot.title == "Example Search Page"
    assert snapshot.dom_excerpt is not None
    assert "input" in snapshot.dom_excerpt.lower()
    assert "button" in snapshot.dom_excerpt.lower()
    # Hidden elements and scripts should be removed
    assert "hidden" not in snapshot.dom_excerpt.lower()
    assert "script" not in snapshot.dom_excerpt.lower()
    assert snapshot.console_logs is not None
    assert len(snapshot.console_logs) > 0
    assert "deprecated" in snapshot.console_logs[0].lower()


@pytest.mark.asyncio
async def test_state_observer_dom_cleaning() -> None:
    """Test that DOM cleaning removes unnecessary content."""
    mock_mcp = AsyncMock()
    
    async def mock_call(*, tool_candidates: list[str], arguments: dict) -> ToolResult:
        if _has_candidate(tool_candidates, "snapshot", "dom"):
            return ToolResult(
                ok=True,
                error=None,
                raw={
                    "content": [
                        {
                            "text": """
                            <div hidden>Hidden</div>
                            <input style="width: 100px;" data-id="123" data-secret="xyz" />
                            <button aria-label="Submit" aria-hidden="false">Click</button>
                            <script>var secret = "password";</script>
                            <style>body { color: blue; }</style>
                            """
                        }
                    ]
                },
            )
        return ToolResult(ok=False, error=None, raw=None)
    
    mock_mcp.call = mock_call
    
    observer = StateObserver(mcp_client=mock_mcp)
    snapshot = await observer.snapshot()
    
    # Verify cleaning removed unwanted content
    assert snapshot.dom_excerpt is not None
    cleaned = snapshot.dom_excerpt.lower()
    assert "script" not in cleaned
    assert "style" not in cleaned
    assert "data-secret" not in cleaned
    assert "hidden" not in cleaned  # The hidden div should be removed
    # But interactive elements and labels should remain
    assert "button" in cleaned
    assert "input" in cleaned


@pytest.mark.asyncio
async def test_state_observer_handles_missing_tools() -> None:
    """Test that StateObserver gracefully handles missing MCP tools."""
    mock_mcp = AsyncMock()
    
    async def mock_call(*, tool_candidates: list[str], arguments: dict) -> ToolResult:
        # Simulate all tools failing
        return ToolResult(ok=False, error=f"Tool not found", raw=None)
    
    mock_mcp.call = mock_call
    
    observer = StateObserver(mcp_client=mock_mcp)
    snapshot = await observer.snapshot()
    
    # Should still return a valid snapshot with fallback values
    assert snapshot.url == "about:blank"
    assert snapshot.title is None
    assert snapshot.dom_excerpt is None
    assert snapshot.console_logs is None


@pytest.mark.asyncio
async def test_state_observer_truncates_large_dom() -> None:
    """Test that large DOM is truncated to prevent overwhelming the LLM."""
    mock_mcp = AsyncMock()
    
    # Create a very large DOM
    large_dom = "<div>" + ("<p>Content</p>" * 2000) + "</div>"
    
    async def mock_call(*, tool_candidates: list[str], arguments: dict) -> ToolResult:
        if _has_candidate(tool_candidates, "snapshot", "dom"):
            return ToolResult(
                ok=True,
                error=None,
                raw={"content": [{"text": large_dom}]},
            )
        return ToolResult(ok=False, error=None, raw=None)
    
    mock_mcp.call = mock_call
    
    observer = StateObserver(mcp_client=mock_mcp)
    snapshot = await observer.snapshot()
    
    # Verify DOM is truncated
    assert snapshot.dom_excerpt is not None
    assert len(snapshot.dom_excerpt) <= 8100  # 8000 + truncation message
    assert "(truncated)" in snapshot.dom_excerpt


@pytest.mark.asyncio
async def test_state_observer_formats_console_logs() -> None:
    """Test that console logs are properly formatted."""
    mock_mcp = AsyncMock()
    
    async def mock_call(*, tool_candidates: list[str], arguments: dict) -> ToolResult:
        if _has_candidate(tool_candidates, "console"):
            # Return JSON array of console messages
            return ToolResult(
                ok=True,
                error=None,
                raw={
                    "content": [
                        {
                            "text": '["Error: ReferenceError", "Warning: deprecated", "Info: loaded"]'
                        }
                    ]
                },
            )
        return ToolResult(ok=False, error=None, raw=None)
    
    mock_mcp.call = mock_call
    
    observer = StateObserver(mcp_client=mock_mcp)
    snapshot = await observer.snapshot()
    
    # Verify console logs are parsed correctly
    assert snapshot.console_logs is not None
    assert len(snapshot.console_logs) == 3
    assert any("Error" in log for log in snapshot.console_logs)
    assert any("Warning" in log for log in snapshot.console_logs)


@pytest.mark.asyncio
async def test_state_observer_saves_screenshot() -> None:
    """Test that screenshots are saved to artifacts folder."""
    import base64
    import os
    import tempfile
    from pathlib import Path
    
    mock_mcp = AsyncMock()
    
    # Create a small valid PNG (1x1 transparent pixel)
    png_data = base64.b64encode(
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
        b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    ).decode('ascii')
    
    async def mock_call(*, tool_candidates: list[str], arguments: dict) -> ToolResult:
        if _has_candidate(tool_candidates, "screenshot"):
            return ToolResult(
                ok=True,
                error=None,
                raw={"content": [{"text": png_data}]},
            )
        return ToolResult(ok=False, error=None, raw=None)
    
    mock_mcp.call = mock_call
    
    # Use a temporary directory for artifacts
    with tempfile.TemporaryDirectory() as tmpdir:
        observer = StateObserver(mcp_client=mock_mcp)
        observer._artifacts_dir = tmpdir
        snapshot = await observer.snapshot()
        
        # Verify screenshot was saved
        assert snapshot.screenshot_path is not None
        assert os.path.exists(os.path.join(tmpdir, snapshot.screenshot_path))
        assert snapshot.screenshot_path.endswith('.png')
