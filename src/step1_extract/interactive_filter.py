from __future__ import annotations

from src.config.schemas import SelectorKind
from src.step1_extract.models import SelectorRecord


class InteractiveElementFilter:
    """Step 1 filter contract for interactive DOM nodes only."""

    def filter(self, records: list[SelectorRecord]) -> list[SelectorRecord]:
        interactive_kinds = {
            SelectorKind.FORM,
            SelectorKind.INPUT,
            SelectorKind.TEXTAREA,
            SelectorKind.SELECT,
            SelectorKind.BUTTON,
            SelectorKind.LINK,
            SelectorKind.SEARCH,
        }

        seen_selectors: set[str] = set()
        filtered: list[SelectorRecord] = []
        for record in records:
            if record.kind not in interactive_kinds:
                continue
            if not record.is_enabled:
                continue
            if not record.is_visible and record.kind not in {SelectorKind.FORM, SelectorKind.LINK}:
                continue
            if record.selector in seen_selectors:
                continue

            seen_selectors.add(record.selector)
            filtered.append(record)

        return filtered
