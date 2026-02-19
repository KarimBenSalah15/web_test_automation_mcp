from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentMemory:
    prompt: str
    test_plan: dict[str, Any]
    step_index: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    last_error: str | None = None
    success: bool = False

    def push(self, event: dict[str, Any]) -> None:
        self.history.append(event)
