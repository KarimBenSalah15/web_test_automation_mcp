# Selector Refiner implementation that takes the initial candidate selectors and metadata,
# and applies an LLM-based refinement step to produce a cleaner, semantically labeled set of selectors.
from __future__ import annotations

import json
import os

import httpx

from src.step1_extract.models import SelectorRecord


class SelectorRefiner:
    """LLM pass for semantic selector refinement using Gemini."""

    def __init__(self, *, model: str | None = None, timeout_seconds: float = 30.0) -> None:
        self._model = model or os.getenv("STEP1_MODEL", "gemini-3.1-flash-lite")
        self._timeout_seconds = timeout_seconds

    async def refine(
        self,
        *,
        objective: str,
        url: str,
        records: list[SelectorRecord],
    ) -> dict:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Missing GEMINI_API_KEY for Step 1 selector refinement")

        prompt = self._build_prompt(objective=objective, url=url, records=records)
        raw = await self._call_gemini(prompt=prompt, api_key=api_key)
        text = self._extract_response_text(raw)
        return self._parse_refiner_json(text)

    async def _call_gemini(self, *, prompt: str, api_key: str) -> dict:
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent"
            f"?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()

    def _build_prompt(self, *, objective: str, url: str, records: list[SelectorRecord]) -> str:
        compact_records = [
            {
                "selector_id": record.selector_id,
                "selector": record.selector,
                "kind": record.kind.value,
                "label": record.label,
                "placeholder": record.placeholder,
                "text": record.text,
                "name_attr": record.name_attr,
                "is_visible": record.is_visible,
                "is_enabled": record.is_enabled,
            }
            for record in records
        ]

        return (
            "You are refining web testing selectors.\n"
            "Return STRICT JSON only with top-level key 'records'.\n"
            "No markdown, no explanations, no extra keys outside the schema.\n\n"
            "Schema:\n"
            "{\n"
            "  \"records\": [\n"
            "    {\n"
            "      \"selector_id\": \"semantic role id like search_input or login_submit\",\n"
            "      \"selector\": \"must be one of the provided selectors exactly\",\n"
            "      \"kind\": \"button|link|input|textarea|select|form|search\",\n"
            "      \"llm_role\": \"human readable role\",\n"
            "      \"is_fragile\": true or false,\n"
            "      \"suggested_selector\": \"stable alternative selector or null\"\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"Page URL: {url}\n"
            f"Objective: {objective}\n"
            "Candidates:\n"
            + json.dumps(compact_records, ensure_ascii=False, indent=2)
        )

    @staticmethod
    def _extract_response_text(raw: dict) -> str:
        candidates = raw.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise RuntimeError("Gemini returned empty content parts")

        text = parts[0].get("text", "")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Gemini did not return JSON text")
        return text.strip()

    @staticmethod
    def _parse_refiner_json(text: str) -> dict:
        candidate = text.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if len(lines) >= 3:
                candidate = "\n".join(lines[1:-1]).strip()

        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Refiner returned invalid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Refiner JSON root must be an object")
        return payload
