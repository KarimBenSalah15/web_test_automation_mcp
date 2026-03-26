from __future__ import annotations

import json
from pathlib import Path

from src.step4_log.models import RunTrace
from src.step4_log.summarizer import RunSummarizer


class JsonFileStep4Logger:
    def __init__(self, artifacts_root: Path, *, summarizer: RunSummarizer | None = None) -> None:
        self._artifacts_root = artifacts_root
        self._summarizer = summarizer or RunSummarizer()

    async def write(self, *, trace: RunTrace) -> None:
        run_dir = self._artifacts_root / trace.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        trace_path = run_dir / "execution_trace.json"
        execution_trace = trace.to_execution_trace()
        trace_path.write_text(
            json.dumps(execution_trace.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self._summarizer.write(trace=trace, run_dir=run_dir)
