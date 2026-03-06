from __future__ import annotations

from pydantic import Field

from src.config.providers import ProviderMatrix
from src.config.schemas import Duration, JsonSchemaModel, Status, UrlTarget
from src.step1_extract.models import SelectorMap
from src.step2_generate.models import TestCaseBundle
from src.step3_execute.models import ExecutionBatchResult


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
