from __future__ import annotations

from src.step1_extract.models import SelectorMapExtractionResult
from src.step2_generate.models import TestCaseGenerationResult
from src.step3_execute.models import ExecutionBatchResult


class UnimplementedStep3Executor:
    async def run(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
        generation: TestCaseGenerationResult,
    ) -> ExecutionBatchResult:
        raise NotImplementedError("Step 3 executor not implemented yet")
