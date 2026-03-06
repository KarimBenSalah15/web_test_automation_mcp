from __future__ import annotations

from src.config.schemas import JsonSchemaModel


class ReasoningDecision(JsonSchemaModel):
    reasoning: str
    next_action: str
    selector_id: str | None = None
    value: str | None = None


class ReasoningLoop:
    async def decide_next_action(self, *, objective: str, history: list[dict], page_state: dict) -> ReasoningDecision:
        raise NotImplementedError("Reasoning loop not implemented yet")
