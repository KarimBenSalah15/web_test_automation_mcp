from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PipelineStep(str, Enum):
    EXTRACT = "step1_extract"
    GENERATE = "step2_generate"
    EXECUTE = "step3_execute"
    LOG = "step4_log"


class ProviderName(str, Enum):
    GEMINI = "gemini"
    MISTRAL = "mistral"
    GROQ = "groq"
    GITHUB_MODELS = "github_models"
    CEREBRAS = "cerebras"


class ModelAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: ProviderName
    model: str = Field(min_length=1)


class StepProviderPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    primary: ModelAssignment
    fallback: ModelAssignment


class ProviderMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assignments: dict[PipelineStep, StepProviderPolicy]


DEFAULT_PROVIDER_MATRIX = ProviderMatrix(
    assignments={
        PipelineStep.EXTRACT: StepProviderPolicy(
            primary=ModelAssignment(
                provider=ProviderName.GEMINI,
                model="gemini-3.1-flash-lite",
            ),
            fallback=ModelAssignment(
                provider=ProviderName.CEREBRAS,
                model="zai-glm-4.7",
            ),
        ),
        PipelineStep.GENERATE: StepProviderPolicy(
            primary=ModelAssignment(
                provider=ProviderName.CEREBRAS,
                model="zai-glm-4.7",
            ),
            fallback=ModelAssignment(
                provider=ProviderName.MISTRAL,
                model="mistral-large-latest",
            ),
        ),
        PipelineStep.EXECUTE: StepProviderPolicy(
            primary=ModelAssignment(
                provider=ProviderName.GROQ,
                model="llama-3.3-70b-versatile",
            ),
            fallback=ModelAssignment(
                provider=ProviderName.CEREBRAS,
                model="zai-glm-4.7",
            ),
        ),
        PipelineStep.LOG: StepProviderPolicy(
            primary=ModelAssignment(
                provider=ProviderName.GITHUB_MODELS,
                model="grok-3",
            ),
            fallback=ModelAssignment(
                provider=ProviderName.CEREBRAS,
                model="zai-glm-4.7",
            ),
        ),
    }
)
