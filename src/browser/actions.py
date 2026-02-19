from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BrowserAction:
    action_type: str
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    wait_event: str | None = None
    timeout_ms: int = 5000


@dataclass(slots=True)
class ActionResult:
    success: bool
    message: str
    raw: object | None = None
