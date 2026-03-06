import json

import pytest

from src.config.providers import DEFAULT_PROVIDER_MATRIX
from src.config.schemas import Duration, Status
from src.step1_extract.models import SelectorMap
from src.step2_generate import models as generation_models
from src.step3_execute.models import ExecutionBatchResult
from src.step4_log.models import RunTrace
from src.step4_log.writer import JsonFileStep4Logger


@pytest.mark.asyncio
async def test_trace_writer_creates_execution_trace_file(tmp_path) -> None:
    logger = JsonFileStep4Logger(tmp_path)
    trace = RunTrace(
        run_id="run_001",
        target={"url": "https://example.com"},
        objective="Smoke test",
        provider_matrix=DEFAULT_PROVIDER_MATRIX,
        selector_map=SelectorMap(page={"url": "https://example.com"}, records=[]),
        test_cases=generation_models.TestCaseBundle(cases=[]),
        execution=ExecutionBatchResult(status=Status.PASS, results=[]),
        status=Status.PASS,
        duration=Duration(
            started_at_utc="2026-03-06T00:00:00Z",
            ended_at_utc="2026-03-06T00:00:01Z",
            duration_ms=1000,
        ),
    )

    await logger.write(trace=trace)

    trace_path = tmp_path / "run_001" / "execution_trace.json"
    assert trace_path.exists()

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_001"
