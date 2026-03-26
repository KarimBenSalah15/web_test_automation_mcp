import json
import datetime as dt

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
            started_at_utc=dt.datetime(2026, 3, 6, 0, 0, 0, tzinfo=dt.timezone.utc),
            ended_at_utc=dt.datetime(2026, 3, 6, 0, 0, 1, tzinfo=dt.timezone.utc),
            duration_ms=1000,
        ),
    )

    await logger.write(trace=trace)

    run_dir = tmp_path / "run_001"
    trace_path = run_dir / "execution_trace.json"
    summary_path = run_dir / "summary.json"
    assert run_dir.exists()
    assert trace_path.exists()
    assert summary_path.exists()

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_001"
    assert payload["target_url"] == "https://example.com/"
    assert payload["total_duration_ms"] == 1000
    assert payload["overall_status"] == "pass"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["run_id"] == "run_001"
    assert summary["total_test_cases"] == 0
    assert summary["passed_test_cases"] == 0
    assert summary["failed_test_cases"] == 0
    assert summary["overall_status"] == "pass"


@pytest.mark.asyncio
async def test_trace_writer_always_creates_files_when_execution_has_errors(tmp_path) -> None:
    logger = JsonFileStep4Logger(tmp_path)
    trace = RunTrace(
        run_id="run_error",
        target={"url": "https://example.com"},
        objective="Error path",
        provider_matrix=DEFAULT_PROVIDER_MATRIX,
        selector_map=SelectorMap(page={"url": "https://example.com"}, records=[]),
        test_cases=generation_models.TestCaseBundle(cases=[]),
        execution=ExecutionBatchResult(status=Status.ERROR, results=[]),
        status=Status.ERROR,
        error="RuntimeError: Step 3 crashed",
        duration=Duration(
            started_at_utc=dt.datetime(2026, 3, 6, 0, 0, 0, tzinfo=dt.timezone.utc),
            ended_at_utc=dt.datetime(2026, 3, 6, 0, 0, 2, tzinfo=dt.timezone.utc),
            duration_ms=2000,
        ),
    )

    await logger.write(trace=trace)

    run_dir = tmp_path / "run_error"
    trace_path = run_dir / "execution_trace.json"
    summary_path = run_dir / "summary.json"
    assert run_dir.exists()
    assert trace_path.exists()
    assert summary_path.exists()

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["overall_status"] == "error"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["overall_status"] == "error"
