import pytest

from src.step1_extract.models import SelectorRecord
from src.step1_extract.selector_refiner import SelectorRefiner


class _MockGeminiRefiner(SelectorRefiner):
    async def _call_gemini(self, *, prompt: str, api_key: str) -> dict:
        assert "STRICT JSON only" in prompt
        assert api_key == "test-key"
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": """{
  \"records\": [
    {
      \"selector_id\": \"search_input\",
      \"selector\": \"#q\",
      \"kind\": \"search\",
      \"llm_role\": \"search_input\",
      \"is_fragile\": false,
      \"suggested_selector\": null
    },
    {
      \"selector_id\": \"search_submit\",
      \"selector\": \"button[type='submit']\",
      \"kind\": \"button\",
      \"llm_role\": \"search_submit\",
      \"is_fragile\": true,
      \"suggested_selector\": \"#searchForm button[type='submit']\"
    }
  ]
}"""
                            }
                        ]
                    }
                }
            ]
        }


@pytest.mark.asyncio
async def test_selector_refiner_parses_mocked_gemini_json(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    refiner = _MockGeminiRefiner(model="gemini-3-flash-preview")
    payload = await refiner.refine(
        objective="Search for mesh routers",
        url="https://example.com",
        records=[
            SelectorRecord(
                selector_id="search_q",
                selector="#q",
                kind="search",
                is_enabled=True,
                is_visible=True,
            ),
            SelectorRecord(
                selector_id="submit_btn",
                selector="button[type='submit']",
                kind="button",
                is_enabled=True,
                is_visible=True,
            ),
        ],
    )

    assert "records" in payload
    assert isinstance(payload["records"], list)
    assert len(payload["records"]) == 2
    assert payload["records"][0]["selector_id"] == "search_input"
    assert payload["records"][1]["is_fragile"] is True
