from __future__ import annotations

from src.config.schemas import JsonSchemaModel


class ActionRequest(JsonSchemaModel):
    action: str
    selector: str | None = None
    value: str | None = None


class ActionResult(JsonSchemaModel):
    ok: bool
    error: str | None = None


class ActionDispatcher:
    async def dispatch(self, request: ActionRequest) -> ActionResult:
        raise NotImplementedError("Action dispatch not implemented yet")
