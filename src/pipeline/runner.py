from __future__ import annotations

import datetime as dt
import json
from typing import Protocol

from pydantic import TypeAdapter

from src.config.schemas import Duration, Status, UrlTarget
from src.config.settings import RuntimeSettings
from src.pipeline.context import PipelineContext
from src.step1_extract.models import SelectorMap
from src.step1_extract.models import SelectorMapExtractionResult
from src.step2_generate.models import TestCaseBundle
from src.step2_generate.models import TestCaseGenerationResult, validate_cases_against_selector_map
from src.step3_execute.models import ExecutionBatchResult
from src.step4_log.models import RunTrace


class Step1Extractor(Protocol):
    async def run(self, *, url: str, objective: str) -> SelectorMapExtractionResult:
        ...


class Step2Generator(Protocol):
    async def run(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
    ) -> TestCaseGenerationResult:
        ...


class Step3Executor(Protocol):
    async def run(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
        generation: TestCaseGenerationResult,
    ) -> ExecutionBatchResult:
        ...


class Step4Logger(Protocol):
    async def write(self, *, trace: RunTrace) -> None:
        ...


class LinearPipelineRunner:
    """Strict linear runner: Step 1 -> Step 2 -> Step 3 -> Step 4."""

    def __init__(
        self,
        *,
        settings: RuntimeSettings,
        step1: Step1Extractor,
        step2: Step2Generator,
        step3: Step3Executor,
        step4: Step4Logger,
    ) -> None:
        self._settings = settings
        self._step1 = step1
        self._step2 = step2
        self._step3 = step3
        self._step4 = step4

    async def run(self, *, run_id: str, url: str, objective: str) -> RunTrace:
        context = PipelineContext(
            run_id=run_id,
            url=url,
            objective=objective,
            settings=self._settings,
        )

        start = context.run_started_at_utc
        status = Status.PASS
        error: str | None = None

        try:
            context.extraction = await self._step1.run(url=url, objective=objective)
            self._print_step1_summary(context.extraction)
            self._write_json(
                path=context.run_dir / "selector_map.json",
                payload=context.extraction.selector_map.model_dump(mode="json"),
            )

            context.generation = await self._step2.run(
                objective=objective,
                extraction=context.extraction,
            )
            context.generation = validate_cases_against_selector_map(
                context.generation,
                context.extraction.selector_map,
            )
            if context.generation.validation_errors:
                raise ValueError(
                    "Selector whitelist validation failed: "
                    + "; ".join(context.generation.validation_errors)
                )
            self._write_json(
                path=context.run_dir / "test_cases.json",
                payload=context.generation.bundle.model_dump(mode="json"),
            )

            context.execution = await self._step3.run(
                objective=objective,
                extraction=context.extraction,
                generation=context.generation,
            )
            if context.execution.status in {Status.FAIL, Status.ERROR}:
                status = context.execution.status
        except Exception as exc:
            status = Status.ERROR
            error = f"{type(exc).__name__}: {exc}"

        end = dt.datetime.now(dt.timezone.utc)
        duration = Duration(
            started_at_utc=start,
            ended_at_utc=end,
            duration_ms=max(0, int((end - start).total_seconds() * 1000)),
        )

        extraction = context.extraction or SelectorMapExtractionResult(
            selector_map=SelectorMap(page={"url": url}, records=[]),
            rejected_candidates=[],
        )
        generation = context.generation or TestCaseGenerationResult(
            bundle=TestCaseBundle(cases=[]),
            validation_errors=[],
        )
        execution = context.execution or ExecutionBatchResult(
            status=Status.ERROR,
            results=[],
        )

        selector_map_path = context.run_dir / "selector_map.json"
        test_cases_path = context.run_dir / "test_cases.json"
        if not selector_map_path.exists():
            self._write_json(path=selector_map_path, payload=extraction.selector_map.model_dump(mode="json"))
        if not test_cases_path.exists():
            self._write_json(path=test_cases_path, payload=generation.bundle.model_dump(mode="json"))

        trace = RunTrace(
            run_id=run_id,
            target=TypeAdapter(UrlTarget).validate_python({"url": url}),
            objective=objective,
            provider_matrix=self._settings.provider_matrix,
            selector_map=extraction.selector_map,
            test_cases=generation.bundle,
            execution=execution,
            status=status,
            error=error,
            duration=duration,
        )

        await self._step4.write(trace=trace)
        return trace

    def _print_step1_summary(self, extraction: SelectorMapExtractionResult) -> None:
        """Print human-readable Step 1 extraction summary to console."""
        from collections import defaultdict

        selector_map = extraction.selector_map
        records = selector_map.records
        rejected = extraction.rejected_candidates

        print("\n" + "=" * 70)
        print("STEP 1: SELECTOR EXTRACTION SUMMARY")
        print("=" * 70)

        # Summary counts
        print(f"\n✓ Extracted: {len(records)} interactive element(s)")
        if rejected:
            print(f"✗ Discarded: {len(rejected)} element(s)")
        else:
            print(f"✗ Discarded: 0 elements")

        # Group by kind for better readability
        by_kind = defaultdict(list)
        for record in records:
            by_kind[record.kind.value].append(record)

        if records:
            print(f"\nElements by type:")
            for kind in sorted(by_kind.keys()):
                items = by_kind[kind]
                print(f"\n  {kind.upper()} ({len(items)}):")
                for record in items:
                    role = record.llm_role or "unknown"
                    selector_preview = (
                        record.selector[:50] + "..." if len(record.selector) > 50 else record.selector
                    )
                    print(f"    - {record.selector_id:30} | {role:20} | {selector_preview}")

        if rejected:
            print(f"\nDiscarded elements ({len(rejected)}):")
            for reason in rejected[:10]:  # Show first 10
                print(f"  - {reason}")
            if len(rejected) > 10:
                print(f"  ... and {len(rejected) - 10} more")

        print("=" * 70 + "\n")

    @staticmethod
    def _write_json(*, path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
