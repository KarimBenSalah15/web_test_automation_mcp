"""Unit tests for Step 2 test case generation."""
from __future__ import annotations

import pytest

from src.config.schemas import SelectorKind, UrlTarget
from src.step1_extract.models import SelectorMap, SelectorMapExtractionResult, SelectorRecord
from src.step2_generate import CerebrasTestCaseGenerator, Step2Generator, TestCaseRefiner


class _FakeCerebrasGenerator(CerebrasTestCaseGenerator):
    async def _call_cerebras(self, *, prompt: str, api_key: str) -> dict:
        assert "Use ONLY selector_id values" in prompt
        assert "VALID_SELECTOR_IDS" in prompt
        assert "STRICTLY FORBIDDEN to invent" in prompt
        assert api_key == "cerebras-test-key"
        return {
            "choices": [
                {
                    "message": {
                        "content": """{
  "cases": [
    {
      "test_id": "generated_001",
      "objective": "Search for product",
      "steps": [
        {
          "step_id": "type_query",
          "action": "type",
          "selector_id": "search_input",
          "value": "mesh router",
          "timeout_ms": 10000,
          "notes": "Enter search query"
        },
        {
          "step_id": "submit_query",
          "action": "click",
          "selector_id": "search_submit",
          "timeout_ms": 10000,
          "notes": "Submit search"
        }
      ]
    }
  ]
}"""
                    }
                }
            ]
        }


class _FakeTestCaseRefiner(TestCaseRefiner):
    async def _call_mistral(self, *, prompt: str, api_key: str) -> dict:
        assert "GENERATED_CASES_JSON" in prompt
        assert api_key == "test-key"
        return {
            "choices": [
                {
                    "message": {
                        "content": """{
  "cases": [
    {
      "test_id": "generated_001",
      "objective": "Search for product",
      "steps": [
        {
          "step_id": "type_query",
          "action": "type",
          "selector_id": "search_input",
          "value": "mesh router",
          "timeout_ms": 10000,
          "notes": "Type query"
        },
        {
          "step_id": "submit_query",
          "action": "click",
          "selector_id": "search_submit",
          "timeout_ms": 10000,
          "notes": "Submit"
        }
      ]
    }
  ]
}"""
                    }
                }
            ]
        }


@pytest.mark.asyncio
async def test_step2_generator_creates_and_refines_test_cases(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-test-key")

    selector_map = SelectorMap(
        page=UrlTarget(url="https://example.com"),
        records=[
            SelectorRecord(
                selector_id="search_input",
                selector="#search-input",
                kind=SelectorKind.INPUT,
                llm_role="user_input",
                text="Search",
                is_visible=True,
                is_enabled=True,
            ),
            SelectorRecord(
                selector_id="search_submit",
                selector='button[type="submit"]',
                kind=SelectorKind.BUTTON,
                llm_role="action",
                text="Search",
                is_visible=True,
                is_enabled=True,
            ),
        ],
    )

    extraction_result = SelectorMapExtractionResult(
        selector_map=selector_map,
        rejected_candidates=[],
    )

    generator = Step2Generator(
        generator_llm=_FakeCerebrasGenerator(),
        refiner=_FakeTestCaseRefiner(),
    )
    result = await generator.run(
        objective="Test search functionality",
        extraction=extraction_result,
    )

    assert result.bundle.cases
    assert len(result.bundle.cases) == 1
    assert result.bundle.cases[0].test_id == "generated_001"
    assert len(result.bundle.cases[0].steps) == 2
    assert result.bundle.cases[0].steps[0].selector_id == "search_input"
    assert result.bundle.cases[0].steps[1].selector_id == "search_submit"
    assert len(result.validation_errors) == 0


@pytest.mark.asyncio
async def test_step2_generator_detects_unknown_selectors(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-test-key")

    selector_map = SelectorMap(
        page=UrlTarget(url="https://example.com"),
        records=[
            SelectorRecord(
                selector_id="search_input",
                selector="#search-input",
                kind=SelectorKind.INPUT,
                is_visible=True,
                is_enabled=True,
            ),
        ],
    )

    extraction_result = SelectorMapExtractionResult(
        selector_map=selector_map,
        rejected_candidates=[],
    )

    class _FakeBadGenerator(CerebrasTestCaseGenerator):
        async def _call_cerebras(self, *, prompt: str, api_key: str) -> dict:
            assert api_key == "cerebras-test-key"
            return {
                "choices": [
                    {
                        "message": {
                            "content": """{
  "cases": [
    {
      "test_id": "bad_generated",
      "objective": "Test",
      "steps": [
        {
          "step_id": "click_unknown",
          "action": "click",
          "selector_id": "unknown_button",
          "timeout_ms": 10000,
          "notes": "Click unknown button"
        }
      ]
    }
  ]
}"""
                        }
                    }
                ]
            }

    class _PassThroughRefiner(TestCaseRefiner):
        async def _call_mistral(self, *, prompt: str, api_key: str) -> dict:
            assert api_key == "test-key"
            return {
                "choices": [
                    {
                        "message": {
                            "content": """{
  "cases": [
    {
      "test_id": "bad_generated",
      "objective": "Test",
      "steps": [
        {
          "step_id": "click_unknown",
          "action": "click",
          "selector_id": "unknown_button",
          "timeout_ms": 10000,
          "notes": "Click unknown button"
        }
      ]
    }
  ]
}"""
                        }
                    }
                ]
            }

    generator = Step2Generator(
        generator_llm=_FakeBadGenerator(),
        refiner=_PassThroughRefiner(),
    )
    result = await generator.run(objective="Test", extraction=extraction_result)

    assert len(result.validation_errors) > 0
    assert any("unknown_button" in error for error in result.validation_errors)


@pytest.mark.asyncio
async def test_step2_generator_pre_whitelist_check_logs_hallucinations(monkeypatch, capsys):
    """Verify that pre-whitelist check logs provided vs returned selector_ids."""
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-test-key")

    selector_map = SelectorMap(
        page=UrlTarget(url="https://example.com"),
        records=[
            SelectorRecord(
                selector_id="search_input",
                selector="#search-input",
                kind=SelectorKind.INPUT,
                is_visible=True,
                is_enabled=True,
            ),
            SelectorRecord(
                selector_id="search_submit",
                selector='button[type="submit"]',
                kind=SelectorKind.BUTTON,
                is_visible=True,
                is_enabled=True,
            ),
        ],
    )

    extraction_result = SelectorMapExtractionResult(
        selector_map=selector_map,
        rejected_candidates=[],
    )

    class _FakeHallucinatingGenerator(CerebrasTestCaseGenerator):
        async def _call_cerebras(self, *, prompt: str, api_key: str) -> dict:
            # LLM hallucinates unknown_button selector_id
            return {
                "choices": [
                    {
                        "message": {
                            "content": """{
  "cases": [
    {
      "test_id": "hallucinated_001",
      "objective": "Test",
      "steps": [
        {
          "step_id": "type_query",
          "action": "type",
          "selector_id": "search_input",
          "timeout_ms": 10000,
          "notes": "Type query"
        },
        {
          "step_id": "click_hallucinated",
          "action": "click",
          "selector_id": "submit_button_fake",
          "timeout_ms": 10000,
          "notes": "Click submit"
        }
      ]
    }
  ]
}"""
                        }
                    }
                ]
            }

    class _PassThroughRefiner(TestCaseRefiner):
        async def _call_mistral(self, *, prompt: str, api_key: str) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": """{
  "cases": [
    {
      "test_id": "hallucinated_001",
      "objective": "Test",
      "steps": [
        {
          "step_id": "type_query",
          "action": "type",
          "selector_id": "search_input",
          "timeout_ms": 10000,
          "notes": "Type query"
        },
        {
          "step_id": "click_hallucinated",
          "action": "click",
          "selector_id": "submit_button_fake",
          "timeout_ms": 10000,
          "notes": "Click submit"
        }
      ]
    }
  ]
}"""
                        }
                    }
                ]
            }

    generator = Step2Generator(
        generator_llm=_FakeHallucinatingGenerator(),
        refiner=_PassThroughRefiner(),
    )

    result = await generator.run(objective="Test", extraction=extraction_result)

    # Check console output for pre-whitelist check info
    captured = capsys.readouterr()
    assert "Pre-Whitelist Selector ID Check" in captured.out
    assert "Provided selector_ids" in captured.out
    assert "Returned selector_ids" in captured.out
    assert "WARNING" in captured.out or "unknown" in captured.out.lower()

    # Verify validation still catches the error
    assert len(result.validation_errors) > 0

