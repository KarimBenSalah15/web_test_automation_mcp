from __future__ import annotations

from src.config.providers import ModelAssignment, PipelineStep, ProviderMatrix


def resolve_primary_for_step(matrix: ProviderMatrix, step: PipelineStep) -> ModelAssignment:
    return matrix.assignments[step].primary


def resolve_fallback_for_step(matrix: ProviderMatrix, step: PipelineStep) -> ModelAssignment:
    return matrix.assignments[step].fallback
