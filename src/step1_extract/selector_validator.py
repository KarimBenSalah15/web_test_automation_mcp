# Selector Validator implementation that performs post-LLM validation of the refined selector records,
# ensuring that the output from the refiner step adheres to expected structure and that all selectors
# are present in the originally extracted set. This is a crucial step to catch any issues with the LLM output.
from __future__ import annotations

from src.config.schemas import SelectorKind

from src.step1_extract.models import SelectorRecord


class SelectorValidator:
    """Post-LLM validator for structure and selector membership only."""

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

        source_by_selector = {record.selector: record for record in extracted_records}

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
            if selector not in source_by_selector:
                rejected.append(f"records[{idx}] selector not in extracted set: {selector}")
                continue

            source = source_by_selector[selector]

            try:
                kind = SelectorKind(kind_raw) if kind_raw else source.kind
            except ValueError:
                rejected.append(f"records[{idx}] invalid kind: {kind_raw}")
                continue

            if selector_id in seen_ids:
                rejected.append(f"duplicate selector_id: {selector_id}")
                continue
            if selector in seen_selectors:
                rejected.append(f"duplicate selector: {selector}")
                continue

            seen_ids.add(selector_id)
            seen_selectors.add(selector)

            valid.append(
                SelectorRecord(
                    selector_id=selector_id,
                    selector=selector,
                    kind=kind,
                    llm_role=str(raw_item.get("llm_role") or selector_id),
                    label=str(raw_item.get("label") or source.label or "") or None,
                    placeholder=str(raw_item.get("placeholder") or source.placeholder or "") or None,
                    text=str(raw_item.get("text") or source.text or "") or None,
                    name_attr=str(raw_item.get("name_attr") or source.name_attr or "") or None,
                    is_visible=source.is_visible,
                    is_enabled=source.is_enabled,
                    is_fragile=bool(raw_item.get("is_fragile", False)),
                    suggested_selector=(
                        str(raw_item.get("suggested_selector", "")).strip() or None
                    ),
                    source_xpath=source.source_xpath,
                )
            )

        return valid, rejected
