"""Unit tests for Step 2 test case refiner (Mistral API integration)."""
from __future__ import annotations

import pytest

from src.config.schemas import SelectorKind, UrlTarget
from src.step1_extract.models import SelectorMap, SelectorRecord
from src.step2_generate import TestCaseRefiner


class _MockMistralRefiner(TestCaseRefiner):
    """Mock refiner that returns realistic Mistral API response without making network call."""

    async def _call_mistral(self, *, prompt: str, api_key: str) -> dict:
        assert api_key == "test-key"
        return {
            "choices": [
                {
                    "message": {
                        "content": """{
  "cases": [
    {
      "test_id": "test_001_search",
      "objective": "Search for product",
      "steps": [
        {
          "step_id": "input_search",
          "action": "type",
          "selector_id": "search_box",
          "value": "laptop",
          "timeout_ms": 10000,
          "notes": "Type search term"
        },
        {
          "step_id": "submit_search",
          "action": "click",
          "selector_id": "search_button",
          "timeout_ms": 10000,
          "notes": "Click search button"
        },
        {
          "step_id": "wait_results",
          "action": "wait",
          "timeout_ms": 5000,
          "notes": "Wait for results to load"
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
async def test_test_case_refiner_parses_mocked_mistral_json(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    refiner = _MockMistralRefiner()
    selector_map = SelectorMap(
        page=UrlTarget(url="https://example.com"),
        records=[
            SelectorRecord(
                selector_id="search_box",
                selector="#search-box",
                kind=SelectorKind.INPUT,
                is_visible=True,
                is_enabled=True,
            ),
            SelectorRecord(
                selector_id="search_button",
                selector='button[type="submit"]',
                kind=SelectorKind.BUTTON,
                is_visible=True,
                is_enabled=True,
            ),
        ],
    )
    generated_payload = {
      "cases": [
        {
          "test_id": "generated_001",
          "objective": "Search",
          "steps": [
            {
              "step_id": "s1",
              "action": "type",
              "selector_id": "search_box",
              "value": "laptop",
            }
          ],
        }
      ]
    }

    result = await refiner.refine(
        objective="Test search",
        selector_map=selector_map,
      generated_payload=generated_payload,
    )

    assert "cases" in result
    assert len(result["cases"]) == 1
    assert result["cases"][0]["test_id"] == "test_001_search"
    assert len(result["cases"][0]["steps"]) == 3


@pytest.mark.asyncio
async def test_test_case_refiner_handles_markdown_wrapped_json(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    class _MarkdownWrappedRefiner(TestCaseRefiner):
        async def _call_mistral(self, *, prompt: str, api_key: str) -> dict:
            assert api_key == "test-key"
            return {
                "choices": [
                    {
                        "message": {
                            "content": """```json
{
  "cases": [
    {
      "test_id": "test_001",
      "objective": "Test",
      "steps": [
        {
          "step_id": "step_1",
          "action": "wait",
          "timeout_ms": 3000
        }
      ]
    }
  ]
}
```"""
                        }
                    }
                ]
            }

    refiner = _MarkdownWrappedRefiner()
    selector_map = SelectorMap(page=UrlTarget(url="https://example.com"), records=[])
    generated_payload = {"cases": []}

    result = await refiner.refine(
        objective="Test",
        selector_map=selector_map,
      generated_payload=generated_payload,
    )

    assert "cases" in result
    assert len(result["cases"]) == 1
    assert result["cases"][0]["test_id"] == "test_001"
