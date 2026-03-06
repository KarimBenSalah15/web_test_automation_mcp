from __future__ import annotations

from src.config.schemas import JsonSchemaModel, Status
from src.step4_log.models import RunTrace


class RunSummary(JsonSchemaModel):
    run_id: str
    status: Status
    total_tests: int
    passed_tests: int
    failed_tests: int
    errored_tests: int


class RunSummarizer:
    def build(self, trace: RunTrace) -> RunSummary:
        total = len(trace.execution.results)
        passed = sum(1 for item in trace.execution.results if item.status == Status.PASS)
        failed = sum(1 for item in trace.execution.results if item.status == Status.FAIL)
        errored = sum(1 for item in trace.execution.results if item.status == Status.ERROR)
        return RunSummary(
            run_id=trace.run_id,
            status=trace.status,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            errored_tests=errored,
        )
