import pytest

from src.config.settings import RuntimeSettings
from src.pipeline.runner import LinearPipelineRunner
from src.step1_extract.extractor import Step1Extractor
from src.step2_generate.generator import UnimplementedStep2Generator
from src.step3_execute.executor import UnimplementedStep3Executor
from src.step4_log.writer import JsonFileStep4Logger


class _FakeStep1Extractor(Step1Extractor):
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


@pytest.mark.asyncio
async def test_linear_pipeline_smoke(tmp_path) -> None:
    runner = LinearPipelineRunner(
        settings=RuntimeSettings(artifacts_root=tmp_path),
        step1=_FakeStep1Extractor(),
        step2=UnimplementedStep2Generator(),
        step3=UnimplementedStep3Executor(),
        step4=JsonFileStep4Logger(tmp_path),
    )

    with pytest.raises(RuntimeError, match="Step 2 generation did not produce output"):
        await runner.run(
            run_id="run_smoke",
            url="https://example.com",
            objective="Smoke objective",
        )
