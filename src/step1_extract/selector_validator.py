from __future__ import annotations

import re

from src.step1_extract.models import SelectorRecord


class SelectorValidator:
    """Step 1 selector validation contract."""

    def validate(self, records: list[SelectorRecord]) -> tuple[list[SelectorRecord], list[str]]:
        valid: list[SelectorRecord] = []
        rejected: list[str] = []

        seen_ids: set[str] = set()
        seen_selectors: set[str] = set()

        for record in records:
            if record.selector_id in seen_ids:
                rejected.append(f"duplicate selector_id: {record.selector_id}")
                continue
            if record.selector in seen_selectors:
                rejected.append(f"duplicate selector: {record.selector}")
                continue
            if not self._is_supported_selector(record.selector):
                rejected.append(f"unsupported selector format: {record.selector}")
                continue

            seen_ids.add(record.selector_id)
            seen_selectors.add(record.selector)
            valid.append(record)

        return valid, rejected

    @staticmethod
    def _is_supported_selector(selector: str) -> bool:
        if not selector:
            return False

        if re.fullmatch(r"#[A-Za-z_][-A-Za-z0-9_:.]*", selector):
            return True

        if re.fullmatch(r"[a-z0-9_-]+\[[a-z0-9_-]+='.*'\]", selector):
            return True

        if re.fullmatch(
            r"[a-z0-9_-]+:nth-of-type\(\d+\)(\s>\s[a-z0-9_-]+:nth-of-type\(\d+\))*",
            selector,
        ):
            return True

        return False
