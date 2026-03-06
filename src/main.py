from __future__ import annotations

import argparse
import asyncio
import datetime as dt

from dotenv import load_dotenv

from src.config.settings import RuntimeSettings
from src.llm.providers import validate_provider_keys
from src.pipeline.runner import LinearPipelineRunner
from src.step1_extract.extractor import UnimplementedStep1Extractor
from src.step2_generate.generator import UnimplementedStep2Generator
from src.step3_execute.executor import UnimplementedStep3Executor
from src.step4_log.writer import JsonFileStep4Logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Linear web test automation pipeline skeleton")
    parser.add_argument("--url", required=True, help="Target page URL")
    parser.add_argument("--objective", required=True, help="Test objective")
    parser.add_argument("--run-id", default="", help="Optional run id")
    return parser.parse_args()


async def _run(url: str, objective: str, run_id: str) -> None:
    load_dotenv()
    settings = RuntimeSettings()
    missing_keys = validate_provider_keys(settings.provider_matrix)
    if missing_keys:
        print("Missing provider API keys in .env: " + ", ".join(missing_keys))

    computed_run_id = run_id or f"run_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    runner = LinearPipelineRunner(
        settings=settings,
        step1=UnimplementedStep1Extractor(),
        step2=UnimplementedStep2Generator(),
        step3=UnimplementedStep3Executor(),
        step4=JsonFileStep4Logger(settings.artifacts_root),
    )

    trace = await runner.run(run_id=computed_run_id, url=url, objective=objective)
    print(f"Run completed with status: {trace.status.value}")
    if trace.error:
        print(f"Error: {trace.error}")


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(url=args.url, objective=args.objective, run_id=args.run_id))
    except RuntimeError as exc:
        print(f"Pipeline skeleton is active but not fully implemented yet: {exc}")


if __name__ == "__main__":
    main()
