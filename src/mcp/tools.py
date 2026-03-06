from __future__ import annotations

from src.config.schemas import JsonSchemaModel


class NavigateArgs(JsonSchemaModel):
    url: str


class ClickArgs(JsonSchemaModel):
    selector: str


class TypeArgs(JsonSchemaModel):
    selector: str
    text: str


class ToolResult(JsonSchemaModel):
    ok: bool
    error: str | None = None
    raw: dict | None = None
