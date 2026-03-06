from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from src.config.schemas import JsonSchemaModel
from src.step1_extract.models import SelectorMap


class TestActionType(str, Enum):
    CLICK = "click"
    TYPE = "type"
    PRESS = "press"
    WAIT = "wait"
    ASSERT_TEXT = "assert_text"
    ASSERT_VISIBLE = "assert_visible"


class TestStep(JsonSchemaModel):
    step_id: str = Field(min_length=1)
    action: TestActionType
    selector_id: str | None = None
    value: str | None = None
    timeout_ms: int = Field(default=10_000, ge=0)
    notes: str | None = None


class TestCase(JsonSchemaModel):
    test_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    steps: list[TestStep] = Field(min_length=1)


class TestCaseBundle(JsonSchemaModel):
    cases: list[TestCase] = Field(default_factory=list)


class TestCaseGenerationResult(JsonSchemaModel):
    bundle: TestCaseBundle
    validation_errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def selectors_must_be_known(self) -> "TestCaseGenerationResult":
        return self


def validate_cases_against_selector_map(
    result: TestCaseGenerationResult,
    selector_map: SelectorMap,
) -> TestCaseGenerationResult:
    known_ids = selector_map.selector_ids()
    errors: list[str] = []
    for test_case in result.bundle.cases:
        for step in test_case.steps:
            if step.selector_id and step.selector_id not in known_ids:
                errors.append(
                    f"Unknown selector_id '{step.selector_id}' in test '{test_case.test_id}' step '{step.step_id}'"
                )

    return TestCaseGenerationResult(
        bundle=result.bundle,
        validation_errors=errors,
    )
