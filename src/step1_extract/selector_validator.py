# Selector Validator implementation that performs post-LLM validation of the refined selector records,
# ensuring that the output from the refiner step adheres to expected structure and that all selector_ids
# are present in the originally extracted set. This is a crucial step to catch any issues with the LLM output.
from __future__ import annotations

import re

from src.config.schemas import SelectorKind

from src.step1_extract.models import SelectorRecord


class SelectorValidator:
    """Post-LLM validator for structure and selector_id membership."""

    def validate(
        self,
        *,
        refined_payload: dict,
        extracted_records: list[SelectorRecord],
    ) -> tuple[list[SelectorRecord], list[str]]:
        if not isinstance(refined_payload, dict):
            return [], ["refiner payload is not a JSON object"]

        raw_records = refined_payload.get("records")
        if not isinstance(raw_records, list):
            return [], ["refiner payload missing 'records' list"]

        source_by_id = {record.selector_id: record for record in extracted_records}

        valid: list[SelectorRecord] = []
        rejected: list[str] = []
        seen_ids: set[str] = set()
        seen_selectors: set[str] = set()

        for idx, raw_item in enumerate(raw_records):
            if not isinstance(raw_item, dict):
                rejected.append(f"records[{idx}] is not an object")
                continue

            selector = str(raw_item.get("selector", "")).strip()
            selector_id = str(raw_item.get("selector_id", "")).strip()
            kind_raw = str(raw_item.get("kind", "")).strip().lower()

            if not selector:
                rejected.append(f"records[{idx}] missing selector")
                continue
            if not selector_id:
                rejected.append(f"records[{idx}] missing selector_id")
                continue
            if selector_id not in source_by_id:
                rejected.append(f"records[{idx}] selector_id not in extracted set: {selector_id}")
                continue

            source = source_by_id[selector_id]
            suggested_selector = str(raw_item.get("suggested_selector", "")).strip() or None
            final_selector = selector

            try:
                kind = SelectorKind(kind_raw) if kind_raw else source.kind
            except ValueError:
                rejected.append(f"records[{idx}] invalid kind: {kind_raw}")
                continue

            is_fragile = bool(raw_item.get("is_fragile", False))
            if is_fragile and self._should_promote_suggested_selector(
                selector=selector,
                suggested_selector=suggested_selector,
            ):
                final_selector = suggested_selector or selector

            if selector_id in seen_ids:
                rejected.append(f"duplicate selector_id: {selector_id}")
                continue
            if final_selector in seen_selectors:
                rejected.append(f"duplicate selector: {final_selector}")
                continue

            seen_ids.add(selector_id)
            seen_selectors.add(final_selector)

            valid.append(
                SelectorRecord(
                    selector_id=selector_id,
                    selector=final_selector,
                    kind=kind,
                    llm_role=str(raw_item.get("llm_role") or selector_id),
                    label=str(raw_item.get("label") or source.label or "") or None,
                    placeholder=str(raw_item.get("placeholder") or source.placeholder or "") or None,
                    text=str(raw_item.get("text") or source.text or "") or None,
                    name_attr=str(raw_item.get("name_attr") or source.name_attr or "") or None,
                    is_visible=source.is_visible,
                    is_enabled=source.is_enabled,
                    is_fragile=is_fragile,
                    suggested_selector=(
                        suggested_selector
                    ),
                    source_xpath=source.source_xpath,
                )
            )

        return valid, rejected

    @staticmethod
    def _should_promote_suggested_selector(*, selector: str, suggested_selector: str | None) -> bool:
        if not suggested_selector:
            return False

        suggested = suggested_selector.strip()
        if not suggested:
            return False

        # Ignore explicit null-ish strings occasionally returned by LLMs.
        if suggested.lower() in {"none", "null", "n/a"}:
            return False

        # Promote only when the original selector looks like a brittle structural path.
        is_structural_path = ":nth-of-type(" in selector or selector.strip().startswith("html")
        if not is_structural_path:
            return False

        # Basic CSS sanity check for suggested selector.
        if " " in suggested and ">" not in suggested and "[" not in suggested and "." not in suggested and "#" not in suggested:
            return False

        if re.search(r"[\n\r\t]", suggested):
            return False

        return True
