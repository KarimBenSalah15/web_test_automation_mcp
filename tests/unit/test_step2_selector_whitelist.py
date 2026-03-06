from src.step1_extract.models import SelectorMap, SelectorRecord
from src.step2_generate import models as generation_models


def test_selector_whitelist_rejects_unknown_selector_ids() -> None:
    selector_map = SelectorMap(
        page={"url": "https://example.com"},
        records=[
            SelectorRecord(selector_id="search_input", selector="input[name='q']", kind="search"),
        ],
    )

    result = generation_models.TestCaseGenerationResult(
        bundle=generation_models.TestCaseBundle(
            cases=[
                generation_models.TestCase(
                    test_id="t1",
                    objective="Search for mesh routers",
                    steps=[
                        generation_models.TestStep(
                            step_id="s1",
                            action=generation_models.TestActionType.TYPE,
                            selector_id="unknown_selector",
                            value="mesh router",
                        )
                    ],
                )
            ]
        )
    )

    validated = generation_models.validate_cases_against_selector_map(result, selector_map)

    assert len(validated.validation_errors) == 1
