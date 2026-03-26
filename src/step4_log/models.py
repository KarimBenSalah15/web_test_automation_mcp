from __future__ import annotations

import datetime as dt
from pydantic import Field

from src.config.providers import ProviderMatrix
from src.config.schemas import Duration, JsonSchemaModel, Status, UrlTarget
from src.step1_extract.models import SelectorMap
from src.step2_generate.models import TestCaseBundle
from src.step3_execute.models import ExecutionBatchResult


class StepExecutionTrace(JsonSchemaModel):
    action: str = Field(min_length=1)
    llm_reasoning: str = Field(min_length=1)
    selector: str | None = None
    status: Status
    error: str | None = None
    screenshot_path: str | None = None


class TestCaseExecutionTrace(JsonSchemaModel):
    name: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    status: Status
    duration_ms: int = Field(ge=0)
    steps: list[StepExecutionTrace] = Field(default_factory=list)


class ExecutionTrace(JsonSchemaModel):
    run_id: str = Field(min_length=1)
    timestamp_utc: dt.datetime
    target_url: str = Field(min_length=1)
    total_duration_ms: int = Field(ge=0)
    overall_status: Status
    test_cases: list[TestCaseExecutionTrace] = Field(default_factory=list)


class RunTrace(JsonSchemaModel):
    run_id: str = Field(min_length=1)
    target: UrlTarget
    objective: str = Field(min_length=1)
    provider_matrix: ProviderMatrix
    selector_map: SelectorMap
    test_cases: TestCaseBundle
    execution: ExecutionBatchResult
    status: Status
    error: str | None = None
    duration: Duration

    def to_execution_trace(self) -> ExecutionTrace:
        objective_by_test_id = {case.test_id: case.objective for case in self.test_cases.cases}
        test_case_entries: list[TestCaseExecutionTrace] = []

        for case in self.execution.results:
            steps = [
                StepExecutionTrace(
                    action=step.action,
                    llm_reasoning=step.llm_reasoning,
                    selector=step.selector,
                    status=step.status,
                    error=step.error,
                    screenshot_path=step.screenshot_path,
                )
                for step in case.steps
            ]
            test_case_entries.append(
                TestCaseExecutionTrace(
                    name=case.test_id,
                    objective=objective_by_test_id.get(case.test_id, "n/a"),
                    status=case.status,
                    duration_ms=case.duration.duration_ms,
                    steps=steps,
                )
            )

        return ExecutionTrace(
            run_id=self.run_id,
            timestamp_utc=self.duration.started_at_utc,
            target_url=str(self.target.url),
            total_duration_ms=self.duration.duration_ms,
            overall_status=self.status,
            test_cases=test_case_entries,
        )


class RunSummary(JsonSchemaModel):
    run_id: str = Field(min_length=1)
    total_test_cases: int = Field(ge=0)
    passed_test_cases: int = Field(ge=0)
    failed_test_cases: int = Field(ge=0)
    total_steps_executed: int = Field(ge=0)
    total_retries: int = Field(ge=0)
    overall_status: Status
    total_duration_ms: int = Field(ge=0)
