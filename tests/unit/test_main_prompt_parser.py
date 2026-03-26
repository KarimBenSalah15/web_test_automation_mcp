import pytest

from src.main import PromptIntentParser


class _MockPromptIntentParser(PromptIntentParser):
    def __init__(self, *, payload: str) -> None:
        super().__init__(model="llama-3.1-8b-instant")
        self._payload = payload

    async def _call_groq(self, *, prompt: str, api_key: str) -> dict:
        assert "Return STRICT JSON only" in prompt
        assert api_key == "test-groq-key"
        return {
            "choices": [
                {
                    "message": {
                        "content": self._payload,
                    }
                }
            ]
        }


@pytest.mark.asyncio
async def test_prompt_parser_extracts_explicit_url(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    parser = _MockPromptIntentParser(
        payload='{"url":"https://duckduckgo.com","objective":"Search for inetum and verify top results."}'
    )

    intent = await parser.parse_prompt(prompt="Go to https://duckduckgo.com and search inetum")

    assert intent.url == "https://duckduckgo.com"
    assert "Search" in intent.objective


@pytest.mark.asyncio
async def test_prompt_parser_infres_implicit_url(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    parser = _MockPromptIntentParser(
        payload='{"url":"https://www.google.com","objective":"Search Google for inetum and return the 3 best results."}'
    )

    intent = await parser.parse_prompt(prompt="google inetum and give me the 3 best results")

    assert intent.url == "https://www.google.com"
    assert "Search Google" in intent.objective


@pytest.mark.asyncio
async def test_prompt_parser_rejects_unresolvable_prompt(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    parser = _MockPromptIntentParser(
        payload='{"url":"","objective":"The user request is ambiguous."}'
    )

    with pytest.raises(ValueError) as exc:
        await parser.parse_prompt(prompt="do the thing")

    assert "Could not resolve a starting URL" in str(exc.value)
