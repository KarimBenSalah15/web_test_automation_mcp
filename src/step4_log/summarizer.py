from __future__ import annotations

import json
from pathlib import Path

from src.config.schemas import Status
from src.step4_log.models import RunTrace
from src.step4_log.models import RunSummary


class RunSummarizer:
    def build(self, trace: RunTrace) -> RunSummary:
        total_tests = len(trace.execution.results)
        passed_tests = sum(1 for item in trace.execution.results if item.status == Status.PASS)
        failed_tests = sum(1 for item in trace.execution.results if item.status in {Status.FAIL, Status.ERROR})
        total_steps = sum(len(item.steps) for item in trace.execution.results)
        total_retries = sum(
            1
            for item in trace.execution.results
            for step in item.steps
            if step.fallback_used
        )
        return RunSummary(
            run_id=trace.run_id,
            total_test_cases=total_tests,
            passed_test_cases=passed_tests,
            failed_test_cases=failed_tests,
            total_steps_executed=total_steps,
            total_retries=total_retries,
            overall_status=trace.status,
            total_duration_ms=trace.duration.duration_ms,
        )

    def write(self, *, trace: RunTrace, run_dir: Path) -> RunSummary:
        summary = self.build(trace)
        summary_path = run_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary
