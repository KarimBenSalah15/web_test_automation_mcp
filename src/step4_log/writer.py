from __future__ import annotations

import json
from pathlib import Path

from src.step4_log.models import RunTrace


class JsonFileStep4Logger:
    def __init__(self, artifacts_root: Path) -> None:
        self._artifacts_root = artifacts_root

    async def write(self, *, trace: RunTrace) -> None:
        run_dir = self._artifacts_root / trace.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        trace_path = run_dir / "execution_trace.json"
        trace_path.write_text(
            json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
