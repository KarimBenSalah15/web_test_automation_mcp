from __future__ import annotations

from src.step1_extract.models import SelectorMapExtractionResult
from src.step2_generate.models import TestCaseGenerationResult


class UnimplementedStep2Generator:
    async def run(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
    ) -> TestCaseGenerationResult:
        raise NotImplementedError("Step 2 generator not implemented yet")
