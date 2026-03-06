import pytest

from src.step1_extract.models import SelectorMapExtractionResult
from src.step2_generate import models as generation_models
from src.step3_execute.executor import UnimplementedStep3Executor


@pytest.mark.asyncio
async def test_step3_executor_contract_is_stubbed() -> None:
    executor = UnimplementedStep3Executor()

    with pytest.raises(NotImplementedError):
        await executor.run(
            objective="Any objective",
            extraction=SelectorMapExtractionResult(
                selector_map={"page": {"url": "https://example.com"}, "records": []}
            ),
            generation=generation_models.TestCaseGenerationResult(bundle={"cases": []}),
        )
