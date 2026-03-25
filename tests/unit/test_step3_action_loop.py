import pytest
from unittest.mock import AsyncMock, MagicMock

from src.config.schemas import Status
from src.mcp.client import McpClient
from src.step1_extract.models import SelectorMapExtractionResult
from src.step2_generate import models as generation_models
from src.step3_execute.action_dispatcher import ActionDispatcher, ActionResult
from src.step3_execute.executor import Step3Executor
from src.step3_execute.reasoning_loop import ReasoningDecision, ReasoningLoop
from src.step3_execute.state_observer import PageStateSnapshot, StateObserver


class _FakeReasoner(ReasoningLoop):
    async def decide_next_action(self, *, objective: str, history: list[dict], page_state: dict) -> ReasoningDecision:
        _ = objective
        _ = page_state
        next_action = history[-1]["action"] if history else "type"
        selector_id = history[-1].get("selector_id") if history else "search_input"
        return ReasoningDecision(
            reasoning="Mock reasoning",
            next_action=next_action,
            selector_id=selector_id,
            value=None,
        )


class _FakeMcpClient(McpClient):
    """Stub MCP client for testing."""
    async def call(self, *, tool_candidates: list[str], arguments: dict) -> any:
        from src.mcp.tools import ToolResult
        return ToolResult(ok=True, error=None, raw={"content": [{"text": ""}]})


class _FakeObserver(StateObserver):
    def __init__(self, mcp_client: McpClient | None = None) -> None:
        # Accept mcp_client to match parent signature, but use a fake stub
        super().__init__(mcp_client=mcp_client or _FakeMcpClient())
    
    async def snapshot(self) -> PageStateSnapshot:
        return PageStateSnapshot(
            url="https://example.com",
            title="Example",
            dom_excerpt="<form><input id='q'/><button>Search</button></form>",
            console_logs=None,
            screenshot_path=None,
        )


class _PassingDispatcher(ActionDispatcher):
    async def dispatch(self, request):
        _ = request
        return ActionResult(ok=True, error=None)


class _FailingDispatcher(ActionDispatcher):
    async def dispatch(self, request):
        if request.selector is None:
            return ActionResult(ok=False, error="Missing selector")
        return ActionResult(ok=True, error=None)


@pytest.mark.asyncio
async def test_step3_executor_executes_generated_cases_successfully() -> None:
    executor = Step3Executor(
        reasoning_loop=_FakeReasoner(),
        observer=_FakeObserver(),
        dispatcher=_PassingDispatcher(),
    )

    extraction = SelectorMapExtractionResult(
        selector_map={
            "page": {"url": "https://example.com"},
            "records": [
                {"selector_id": "search_input", "selector": "#q", "kind": "search"},
                {"selector_id": "search_submit", "selector": "button[type='submit']", "kind": "button"},
            ],
        }
    )
    generation = generation_models.TestCaseGenerationResult(
        bundle={
            "cases": [
                {
                    "test_id": "t1",
                    "objective": "search",
                    "steps": [
                        {"step_id": "s1", "action": "type", "selector_id": "search_input", "value": "mesh"},
                        {"step_id": "s2", "action": "click", "selector_id": "search_submit"},
                    ],
                }
            ]
        }
    )

    result = await executor.run(objective="search", extraction=extraction, generation=generation)

    assert result.status == Status.PASS
    assert len(result.results) == 1
    assert result.results[0].status == Status.PASS
    assert len(result.results[0].steps) == 2
    assert result.results[0].steps[0].status == Status.PASS


@pytest.mark.asyncio
async def test_step3_executor_flags_failed_dispatch() -> None:
    executor = Step3Executor(
        reasoning_loop=_FakeReasoner(),
        observer=_FakeObserver(),
        dispatcher=_FailingDispatcher(),
    )

    extraction = SelectorMapExtractionResult(
        selector_map={
            "page": {"url": "https://example.com"},
            "records": [
                {"selector_id": "search_input", "selector": "#q", "kind": "search"},
            ],
        }
    )
    generation = generation_models.TestCaseGenerationResult(
        bundle={
            "cases": [
                {
                    "test_id": "t1",
                    "objective": "search",
                    "steps": [
                        {"step_id": "s1", "action": "type", "selector_id": "unknown_selector", "value": "mesh"},
                    ],
                }
            ]
        }
    )

    result = await executor.run(objective="search", extraction=extraction, generation=generation)

    assert result.status == Status.FAIL
    assert result.results[0].status == Status.FAIL
    assert result.results[0].steps[0].status == Status.FAIL
    assert "Missing selector" in (result.results[0].steps[0].error or "")
