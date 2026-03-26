from __future__ import annotations

import json
import os

import httpx

from src.config.schemas import JsonSchemaModel


class ReasoningDecision(JsonSchemaModel):
    reasoning: str
    next_action: str
    selector_id: str | None = None
    value: str | None = None


class ReasoningLoop:
    def __init__(self, *, model: str | None = None, timeout: float = 20.0) -> None:
        self._model = model or os.getenv("STEP3_MODEL", "llama-3.3-70b-versatile")
        self._timeout_seconds = timeout

    async def decide_next_action(self, *, objective: str, history: list[dict], page_state: dict) -> ReasoningDecision:
        prompt = self._build_prompt(objective=objective, history=history, page_state=page_state)
        errors: list[str] = []

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            try:
                raw = await self._call_groq(prompt=prompt, api_key=groq_key)
                payload = self._parse_json_payload(self._extract_response_text(raw))
                return ReasoningDecision(
                    reasoning=str(payload.get("reasoning", "LLM reasoning unavailable")),
                    next_action=str(payload.get("next_action", "wait")),
                    selector_id=payload.get("selector_id"),
                    value=payload.get("value"),
                )
            except Exception as exc:
                errors.append(f"groq failed: {exc}")
        else:
            errors.append("groq skipped: missing GROQ_API_KEY")

        mistral_key = os.getenv("MISTRAL_API_KEY", "").strip()
        if mistral_key:
            try:
                raw = await self._call_mistral(prompt=prompt, api_key=mistral_key)
                payload = self._parse_json_payload(self._extract_response_text(raw))
                return ReasoningDecision(
                    reasoning=str(payload.get("reasoning", "LLM reasoning unavailable")),
                    next_action=str(payload.get("next_action", "wait")),
                    selector_id=payload.get("selector_id"),
                    value=payload.get("value"),
                )
            except Exception as exc:
                errors.append(f"mistral failed: {exc}")
        else:
            errors.append("mistral skipped: missing MISTRAL_API_KEY")

        last_action = history[-1]["action"] if history else "observe"
        return ReasoningDecision(
            reasoning=(
                f"All Step 3 LLM providers failed ({' | '.join(errors)}). "
                f"Deterministic fallback used after '{last_action}'."
            ),
            next_action=last_action if last_action != "observe" else "wait",
            selector_id=history[-1].get("selector_id") if history else None,
            value=None,
        )

    def _build_prompt(self, *, objective: str, history: list[dict], page_state: dict) -> str:
        return (
            "You are a web-test action reasoner. Return STRICT JSON only.\n"
            "Choose the next action based on current history and page state.\n"
            "OUTPUT_SCHEMA:\n"
            "{\n"
            '  "reasoning": "str",\n'
            '  "next_action": "click|type|press|wait|assert_text|assert_visible",\n'
            '  "selector_id": "str or null",\n'
            '  "value": "str or null"\n'
            "}\n\n"
            f"OBJECTIVE:\n{objective}\n\n"
            f"HISTORY_JSON:\n{json.dumps(history, ensure_ascii=True)}\n\n"
            f"PAGE_STATE_JSON:\n{json.dumps(page_state, ensure_ascii=True)}\n"
        )

    async def _call_groq(self, *, prompt: str, api_key: str) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            return response.json()

    async def _call_mistral(self, *, prompt: str, api_key: str) -> dict:
        model = os.getenv("STEP3_FALLBACK_MODEL", "mistral-large-latest")
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            return response.json()

    def _extract_response_text(self, raw: dict) -> str:
        try:
            return raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Invalid Groq response shape: {exc}")

    def _parse_json_payload(self, text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(line for line in lines[1:-1] if not line.startswith("```"))

        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("Groq reasoning payload must be a JSON object")
        return payload
