from __future__ import annotations

import datetime as dt
import os

from src.config.providers import ModelAssignment, ProviderName
from src.config.schemas import Duration, Status
from src.mcp.client import McpClient
from src.step1_extract.models import SelectorMapExtractionResult
from src.step2_generate.models import TestCaseGenerationResult
from src.step3_execute.action_dispatcher import ActionDispatcher, ActionRequest
from src.step3_execute.models import ActionTrace, ExecutionBatchResult, TestCaseExecutionResult
from src.step3_execute.reasoning_loop import ReasoningLoop
from src.step3_execute.state_observer import StateObserver


class Step3Executor:
    def __init__(
        self,
        *,
        reasoning_loop: ReasoningLoop | None = None,
        dispatcher: ActionDispatcher | None = None,
        observer: StateObserver | None = None,
    ) -> None:
        self._reasoning_loop = reasoning_loop or ReasoningLoop()
        # When a custom dispatcher is injected (e.g. in tests) we don't own
        # the MCP lifecycle. On the production path we create the McpClient,
        # pass it through to the dispatcher and observer, and manage start/stop ourselves.
        if dispatcher is not None:
            self._dispatcher = dispatcher
            self._mcp_client: McpClient | None = None
            self._observer = observer or StateObserver(mcp_client=McpClient())
        else:
            mcp_client = McpClient()
            self._dispatcher = ActionDispatcher(mcp_client=mcp_client)
            self._observer = observer or StateObserver(mcp_client=mcp_client)
            self._mcp_client = mcp_client
        self._model_used = ModelAssignment(
            provider=ProviderName.GROQ,
            model=os.getenv("STEP3_MODEL", "llama-3.3-70b-versatile"),
        )

    async def run(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
        generation: TestCaseGenerationResult,
    ) -> ExecutionBatchResult:
        if self._mcp_client is not None:
            await self._mcp_client.start()
        try:
            return await self._run_inner(
                objective=objective,
                extraction=extraction,
                generation=generation,
            )
        finally:
            if self._mcp_client is not None:
                await self._mcp_client.stop()

    async def _run_inner(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
        generation: TestCaseGenerationResult,
    ) -> ExecutionBatchResult:
        selector_by_id = {
            record.selector_id: record.selector
            for record in extraction.selector_map.records
        }

        case_results: list[TestCaseExecutionResult] = []
        overall_status = Status.PASS

        for test_case in generation.bundle.cases:
            case_start = dt.datetime.now(dt.timezone.utc)
            case_step_traces: list[ActionTrace] = []
            case_status = Status.PASS
            case_error: str | None = None
            history: list[dict] = []

            for step in test_case.steps:
                step_start = dt.datetime.now(dt.timezone.utc)
                page_state = (await self._observer.snapshot()).model_dump()
                decision = await self._reasoning_loop.decide_next_action(
                    objective=objective,
                    history=history,
                    page_state=page_state,
                )

                selected_action = decision.next_action or step.action.value
                selector = selector_by_id.get(step.selector_id or "") if step.selector_id else None

                request = ActionRequest(
                    action=selected_action,
                    selector=selector,
                    value=step.value,
                )
                dispatch_result = await self._dispatcher.dispatch(request)

                step_end = dt.datetime.now(dt.timezone.utc)
                step_status = Status.PASS if dispatch_result.ok else Status.FAIL
                if step_status != Status.PASS and case_status == Status.PASS:
                    case_status = Status.FAIL
                    case_error = dispatch_result.error or f"Action failed at step '{step.step_id}'"

                trace = ActionTrace(
                    test_id=test_case.test_id,
                    step_id=step.step_id,
                    action=selected_action,
                    selector_id=step.selector_id,
                    selector=selector,
                    input_value=step.value,
                    llm_reasoning=decision.reasoning,
                    status=step_status,
                    error=dispatch_result.error,
                    screenshot_path=page_state.get("screenshot_path"),
                    duration=Duration(
                        started_at_utc=step_start,
                        ended_at_utc=step_end,
                        duration_ms=max(0, int((step_end - step_start).total_seconds() * 1000)),
                    ),
                    model_used=self._model_used,
                    fallback_used=False,
                    fallback_reason=None,
                )
                case_step_traces.append(trace)
                history.append(
                    {
                        "step_id": step.step_id,
                        "action": selected_action,
                        "status": step_status.value,
                        "selector_id": step.selector_id,
                    }
                )

            case_end = dt.datetime.now(dt.timezone.utc)
            case_results.append(
                TestCaseExecutionResult(
                    test_id=test_case.test_id,
                    status=case_status,
                    error=case_error,
                    duration=Duration(
                        started_at_utc=case_start,
                        ended_at_utc=case_end,
                        duration_ms=max(0, int((case_end - case_start).total_seconds() * 1000)),
                    ),
                    steps=case_step_traces,
                )
            )

            if case_status == Status.FAIL and overall_status == Status.PASS:
                overall_status = Status.FAIL

        return ExecutionBatchResult(status=overall_status, results=case_results)


class UnimplementedStep3Executor:
    async def run(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
        generation: TestCaseGenerationResult,
    ) -> ExecutionBatchResult:
        raise NotImplementedError("Step 3 executor not implemented yet")
