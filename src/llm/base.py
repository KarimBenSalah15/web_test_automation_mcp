from __future__ import annotations

from typing import Protocol

from src.config.providers import ModelAssignment


class LlmMessage(Protocol):
    role: str
    content: str


class LlmClient(Protocol):
    assignment: ModelAssignment

    async def complete_json(self, *, messages: list[dict[str, str]], schema_name: str) -> dict:
        ...
