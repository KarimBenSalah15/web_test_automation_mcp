# Minimal pre-filter that removes only objectively unusable elements,
# such as those that are not visible or not enabled.
# This is a simple heuristic to reduce the number of candidate selectors
# before applying more complex refinement and validation steps.
from __future__ import annotations

from src.step1_extract.models import SelectorRecord


class InteractiveElementFilter:
    """Minimal pre-filter that removes only objectively unusable elements."""

    def filter(self, records: list[SelectorRecord]) -> list[SelectorRecord]:
        filtered: list[SelectorRecord] = []
        for record in records:
            if not record.is_enabled:
                continue
            if not record.is_visible:
                continue
            filtered.append(record)

        return filtered
