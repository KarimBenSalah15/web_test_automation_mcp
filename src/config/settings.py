from __future__ import annotations

from pathlib import Path

from pydantic import ConfigDict, Field

from src.config.providers import DEFAULT_PROVIDER_MATRIX, ProviderMatrix
from src.config.schemas import JsonSchemaModel


class RuntimeSettings(JsonSchemaModel):
    model_config = ConfigDict(extra="forbid")

    step_timeout_seconds: float = Field(default=45.0, gt=0)
    max_steps_per_test: int = Field(default=30, gt=0)
    artifacts_root: Path = Path("artifacts") / "runs"
    provider_matrix: ProviderMatrix = DEFAULT_PROVIDER_MATRIX
