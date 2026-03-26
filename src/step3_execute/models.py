from __future__ import annotations

from pydantic import Field

from src.config.providers import ModelAssignment
from src.config.schemas import Duration, JsonSchemaModel, Status


class ActionTrace(JsonSchemaModel):
    test_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    selector_id: str | None = None
    selector: str | None = None
    input_value: str | None = None
    llm_reasoning: str = Field(min_length=1)
    status: Status
    error: str | None = None
    screenshot_path: str | None = None
    duration: Duration
    model_used: ModelAssignment
    fallback_used: bool = False
    fallback_reason: str | None = None


class TestCaseExecutionResult(JsonSchemaModel):
    test_id: str = Field(min_length=1)
    status: Status
    error: str | None = None
    duration: Duration
    steps: list[ActionTrace] = Field(default_factory=list)


class ExecutionBatchResult(JsonSchemaModel):
    status: Status
    results: list[TestCaseExecutionResult] = Field(default_factory=list)
