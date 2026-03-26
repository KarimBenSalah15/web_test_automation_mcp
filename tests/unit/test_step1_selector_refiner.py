import pytest

from src.step1_extract.models import SelectorRecord
from src.step1_extract.selector_refiner import SelectorRefiner


class _MockGroqRefiner(SelectorRefiner):
    async def _call_groq(self, *, prompt: str, api_key: str) -> dict:
        assert "STRICT JSON only" in prompt
        assert api_key == "test-key"
        return {
            "choices": [
                {
                    "message": {
                        "content": """{
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
                }
            ]
        }


class _GroqFailureWithFallbackRefiner(SelectorRefiner):
    async def _call_groq(self, *, prompt: str, api_key: str) -> dict:
        _ = prompt
        _ = api_key
        raise RuntimeError("503 Service Unavailable")

    async def _call_mistral(self, *, prompt: str, api_key: str, model: str) -> dict:
        assert "STRICT JSON only" in prompt
        assert api_key == "mistral-test-key"
        assert model == "mistral-large-latest"
        return {
            "choices": [
                {
                    "message": {
                        "content": """{
  \"records\": [
    {
      \"selector_id\": \"search_input\",
      \"selector\": \"#q\",
      \"kind\": \"search\",
      \"llm_role\": \"search_input\",
      \"is_fragile\": false,
      \"suggested_selector\": null
    }
  ]
}"""
                    }
                }
            ]
        }


@pytest.mark.asyncio
async def test_selector_refiner_parses_mocked_groq_json(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    refiner = _MockGroqRefiner(model="llama-3.3-70b-versatile")
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


@pytest.mark.asyncio
async def test_selector_refiner_falls_back_when_groq_fails(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test-key")
    monkeypatch.setenv("STEP1_FALLBACK_PROVIDER", "mistral")
    monkeypatch.setenv("STEP1_FALLBACK_MODEL", "mistral-large-latest")

    refiner = _GroqFailureWithFallbackRefiner(model="llama-3.3-70b-versatile")
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
        ],
    )

    assert "records" in payload
    assert len(payload["records"]) == 1
    assert payload["records"][0]["selector_id"] == "search_input"
