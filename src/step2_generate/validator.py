from __future__ import annotations

from src.step1_extract.models import SelectorMap
from src.step2_generate.models import TestCaseGenerationResult, validate_cases_against_selector_map


class SelectorWhitelistValidator:
    def validate(
        self,
        result: TestCaseGenerationResult,
        selector_map: SelectorMap,
    ) -> TestCaseGenerationResult:
        return validate_cases_against_selector_map(result, selector_map)
