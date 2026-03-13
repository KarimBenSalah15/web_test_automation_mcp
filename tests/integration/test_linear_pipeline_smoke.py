import pytest

from src.config.settings import RuntimeSettings
from src.pipeline.runner import LinearPipelineRunner
from src.step1_extract.extractor import Step1Extractor
from src.step1_extract.selector_refiner import SelectorRefiner
from src.step2_generate.generator import CerebrasTestCaseGenerator, Step2Generator
from src.step2_generate.test_case_refiner import TestCaseRefiner
from src.step3_execute.executor import UnimplementedStep3Executor
from src.step4_log.writer import JsonFileStep4Logger


class _FakeStep1Refiner(SelectorRefiner):
    async def refine(self, *, objective: str, url: str, records: list):
        _ = objective
        _ = url
        return {
            "records": [
                {
                    "selector_id": "search_input",
                    "selector": "#q",
                    "kind": "search",
                    "llm_role": "search_input",
                    "is_fragile": False,
                    "suggested_selector": None,
                },
                {
                    "selector_id": "search_submit",
                    "selector": "button[type='submit']",
                    "kind": "button",
                    "llm_role": "search_submit",
                    "is_fragile": False,
                    "suggested_selector": None,
                },
            ]
        }


class _FakeStep1Extractor(Step1Extractor):
        def __init__(self) -> None:
                super().__init__(refiner=_FakeStep1Refiner())

        async def _fetch_html(self, url: str) -> str:
                _ = url
                return """
                <html>
                    <body>
                        <form id='f1'>
                            <input id='q' name='q' type='search' />
                            <button type='submit'>Search</button>
                        </form>
                    </body>
                </html>
                """


class _FakeStep2Refiner(TestCaseRefiner):
    async def _call_mistral(self, *, prompt: str, api_key: str) -> dict:
        _ = prompt
        _ = api_key
        return {
            "choices": [
                {
                    "message": {
                        "content": """{
  "cases": [
    {
      "test_id": "test_001",
      "objective": "Test search",
      "steps": [
        {
          "step_id": "fill_search",
          "action": "type",
          "selector_id": "search_input",
          "value": "test",
          "timeout_ms": 10000
        },
        {
          "step_id": "click_submit",
          "action": "click",
          "selector_id": "search_submit",
          "timeout_ms": 10000
        }
      ]
    }
  ]
}"""
                    }
                }
            ]
        }


class _FakeStep2GeneratorLLM(CerebrasTestCaseGenerator):
        async def _call_cerebras(self, *, prompt: str, api_key: str) -> dict:
                _ = prompt
                _ = api_key
                return {
                        "choices": [
                                {
                                        "message": {
                                                "content": """{
    "cases": [
        {
            "test_id": "generated_001",
            "objective": "Test search",
            "steps": [
                {
                    "step_id": "fill_search",
                    "action": "type",
                    "selector_id": "search_input",
                    "value": "test",
                    "timeout_ms": 10000
                },
                {
                    "step_id": "click_submit",
                    "action": "click",
                    "selector_id": "search_submit",
                    "timeout_ms": 10000
                }
            ]
        }
    ]
}"""
                                        }
                                }
                        ]
                }


@pytest.mark.asyncio
async def test_linear_pipeline_smoke(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-key")

    runner = LinearPipelineRunner(
        settings=RuntimeSettings(artifacts_root=tmp_path),
        step1=_FakeStep1Extractor(),
        step2=Step2Generator(
            generator_llm=_FakeStep2GeneratorLLM(),
            refiner=_FakeStep2Refiner(),
        ),
        step3=UnimplementedStep3Executor(),
        step4=JsonFileStep4Logger(tmp_path),
    )

    with pytest.raises(RuntimeError, match="Step 3 execution did not produce output"):
        await runner.run(
            run_id="run_smoke",
            url="https://example.com",
            objective="Smoke objective",
        )
