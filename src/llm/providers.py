from __future__ import annotations

import os
from dataclasses import dataclass

from src.config.providers import ModelAssignment, PipelineStep, ProviderName, ProviderMatrix


@dataclass(frozen=True)
class ProviderRuntime:
    assignment: ModelAssignment
    api_key_env: str
    api_key: str


_ENV_BY_PROVIDER: dict[ProviderName, str] = {
    ProviderName.GEMINI: "GEMINI_API_KEY",
    ProviderName.MISTRAL: "MISTRAL_API_KEY",
    ProviderName.GROQ: "GROQ_API_KEY",
    ProviderName.GITHUB_MODELS: "GITHUB_MODELS_API_KEY",
    ProviderName.CEREBRAS: "CEREBRAS_API_KEY",
}


def _build_runtime(assignment: ModelAssignment) -> ProviderRuntime:
    env_name = _ENV_BY_PROVIDER[assignment.provider]
    return ProviderRuntime(
        assignment=assignment,
        api_key_env=env_name,
        api_key=os.getenv(env_name, ""),
    )


def providers_for_step(
    matrix: ProviderMatrix,
    step: PipelineStep,
) -> tuple[ProviderRuntime, ProviderRuntime]:
    policy = matrix.assignments[step]
    primary = _build_runtime(policy.primary)
    fallback = _build_runtime(policy.fallback)
    return primary, fallback


def validate_provider_keys(matrix: ProviderMatrix) -> list[str]:
    missing: list[str] = []
    seen_envs: set[str] = set()

    for policy in matrix.assignments.values():
        for assignment in (policy.primary, policy.fallback):
            env_name = _ENV_BY_PROVIDER[assignment.provider]
            if env_name in seen_envs:
                continue
            seen_envs.add(env_name)
            if not os.getenv(env_name, "").strip():
                missing.append(env_name)

    return sorted(missing)
