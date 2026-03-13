from __future__ import annotations

from src.config.schemas import JsonSchemaModel


class PageStateSnapshot(JsonSchemaModel):
    url: str
    title: str | None = None
    dom_excerpt: str | None = None


class StateObserver:
    async def snapshot(self) -> PageStateSnapshot:
        return PageStateSnapshot(
            url="about:blank",
            title="Execution Context",
            dom_excerpt="Observer placeholder snapshot",
        )
