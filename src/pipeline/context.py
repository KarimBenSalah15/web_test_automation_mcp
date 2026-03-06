from __future__ import annotations

from src.config.settings import RuntimeSettings
from src.step1_extract.models import SelectorMapExtractionResult
from src.step2_generate.models import TestCaseGenerationResult
from src.step3_execute.models import ExecutionBatchResult


class PipelineContext:
    def __init__(
        self,
        *,
        run_id: str,
        url: str,
        objective: str,
        settings: RuntimeSettings,
    ) -> None:
        self.run_id = run_id
        self.url = url
        self.objective = objective
        self.settings = settings

        self.extraction: SelectorMapExtractionResult | None = None
        self.generation: TestCaseGenerationResult | None = None
        self.execution: ExecutionBatchResult | None = None
