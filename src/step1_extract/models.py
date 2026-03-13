# Models for representing selector records, selector maps,
# and extraction results in the Step 1 extraction process.
from __future__ import annotations

from pydantic import Field

from src.config.schemas import JsonSchemaModel, SelectorKind, UrlTarget


class SelectorRecord(JsonSchemaModel):
    selector_id: str = Field(min_length=1)
    selector: str = Field(min_length=1)
    kind: SelectorKind
    llm_role: str | None = None
    label: str | None = None
    placeholder: str | None = None
    text: str | None = None
    name_attr: str | None = None
    is_visible: bool = True
    is_enabled: bool = True
    is_fragile: bool = False
    suggested_selector: str | None = None
    source_xpath: str | None = None


class SelectorMap(JsonSchemaModel):
    page: UrlTarget
    records: list[SelectorRecord] = Field(default_factory=list)

    def selector_ids(self) -> set[str]:
        return {record.selector_id for record in self.records}


class SelectorMapExtractionResult(JsonSchemaModel):
    selector_map: SelectorMap
    rejected_candidates: list[str] = Field(default_factory=list)
