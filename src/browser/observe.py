from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Observation:
    dom: Any
    console: Any
    accessibility: Any
    ocr_text: str

    def has_errors(self) -> bool:
        if isinstance(self.console, list):
            return any("error" in str(entry).lower() for entry in self.console)
        return "error" in str(self.console).lower()
