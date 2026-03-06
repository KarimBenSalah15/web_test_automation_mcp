from __future__ import annotations

import datetime as dt
from typing import Protocol

from pydantic import TypeAdapter

from src.config.schemas import Duration, Status, UrlTarget
from src.config.settings import RuntimeSettings
from src.pipeline.context import PipelineContext
from src.step1_extract.models import SelectorMapExtractionResult
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

        start = dt.datetime.now(dt.timezone.utc)
        status = Status.PASS
        error: str | None = None

        try:
            context.extraction = await self._step1.run(url=url, objective=objective)

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

        if context.extraction is None:
            raise RuntimeError("Step 1 extraction did not produce output")
        if context.generation is None:
            raise RuntimeError("Step 2 generation did not produce output")
        if context.execution is None:
            raise RuntimeError("Step 3 execution did not produce output")

        trace = RunTrace(
            run_id=run_id,
            target=TypeAdapter(UrlTarget).validate_python({"url": url}),
            objective=objective,
            provider_matrix=self._settings.provider_matrix,
            selector_map=context.extraction.selector_map,
            test_cases=context.generation.bundle,
            execution=context.execution,
            status=status,
            error=error,
            duration=duration,
        )

        await self._step4.write(trace=trace)
        return trace
