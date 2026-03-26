from src.step1_extract.models import SelectorRecord
from src.step1_extract.selector_validator import SelectorValidator


def test_validator_promotes_suggested_selector_for_fragile_paths() -> None:
    validator = SelectorValidator()
    extracted = [
        SelectorRecord(
            selector_id="search_input",
            selector="html:nth-of-type(1) > body:nth-of-type(1) > form:nth-of-type(1) > input:nth-of-type(1)",
            kind="input",
            is_visible=True,
            is_enabled=True,
        )
    ]

    refined_payload = {
        "records": [
            {
                "selector_id": "search_input",
                "selector": "html:nth-of-type(1) > body:nth-of-type(1) > form:nth-of-type(1) > input:nth-of-type(1)",
                "kind": "input",
                "llm_role": "search input",
                "is_fragile": True,
                "suggested_selector": "input[name='q']",
            }
        ]
    }

    valid, rejected = validator.validate(refined_payload=refined_payload, extracted_records=extracted)

    assert not rejected
    assert len(valid) == 1
    assert valid[0].selector == "input[name='q']"
    assert valid[0].is_fragile is True


def test_validator_keeps_original_when_suggested_is_invalid_literal_none() -> None:
    validator = SelectorValidator()
    extracted = [
        SelectorRecord(
            selector_id="search_button",
            selector="html:nth-of-type(1) > body:nth-of-type(1) > form:nth-of-type(1) > button:nth-of-type(1)",
            kind="button",
            is_visible=True,
            is_enabled=True,
        )
    ]

    refined_payload = {
        "records": [
            {
                "selector_id": "search_button",
                "selector": "html:nth-of-type(1) > body:nth-of-type(1) > form:nth-of-type(1) > button:nth-of-type(1)",
                "kind": "button",
                "llm_role": "search submit",
                "is_fragile": True,
                "suggested_selector": "None",
            }
        ]
    }

    valid, rejected = validator.validate(refined_payload=refined_payload, extracted_records=extracted)

    assert not rejected
    assert len(valid) == 1
    assert valid[0].selector == "html:nth-of-type(1) > body:nth-of-type(1) > form:nth-of-type(1) > button:nth-of-type(1)"
