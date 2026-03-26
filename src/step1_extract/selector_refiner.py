# Selector Refiner implementation that takes the initial candidate selectors and metadata,
# and applies an LLM-based refinement step to produce a cleaner, semantically labeled set of selectors.
from __future__ import annotations

import json
import os

import httpx

from src.step1_extract.models import SelectorRecord


class SelectorRefiner:
    """LLM pass for semantic selector refinement using Groq (primary) with fallback chain."""

    def __init__(self, *, model: str | None = None, timeout_seconds: float = 30.0) -> None:
        self._model = model or os.getenv("STEP1_MODEL", "llama-3.3-70b-versatile")
        self._timeout_seconds = timeout_seconds

    async def refine(
        self,
        *,
        objective: str,
        url: str,
        records: list[SelectorRecord],
    ) -> dict:
        prompt = self._build_prompt(objective=objective, url=url, records=records)
        errors: list[str] = []

        # Primary: Groq (llama-3.3-70b-versatile)
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            try:
                raw = await self._call_groq(prompt=prompt, api_key=groq_key)
                text = self._extract_openai_response_text(raw)
                return self._parse_refiner_json(text)
            except Exception as exc:
                errors.append(f"groq failed: {exc}")
        else:
            errors.append("groq skipped: missing GROQ_API_KEY")

        # Fallback chain
        fallback_provider = os.getenv("STEP1_FALLBACK_PROVIDER", "mistral").strip().lower()
        try:
            if fallback_provider == "mistral":
                fallback_key = os.getenv("MISTRAL_API_KEY", "").strip()
                if not fallback_key:
                    raise RuntimeError("missing MISTRAL_API_KEY")
                fallback_model = os.getenv("STEP1_FALLBACK_MODEL", "mistral-large-latest")
                raw = await self._call_mistral(prompt=prompt, api_key=fallback_key, model=fallback_model)
                text = self._extract_openai_response_text(raw)
                return self._parse_refiner_json(text)

            if fallback_provider == "cerebras":
                fallback_key = os.getenv("CEREBRAS_API_KEY", "").strip()
                if not fallback_key:
                    raise RuntimeError("missing CEREBRAS_API_KEY")
                fallback_model = os.getenv("STEP1_FALLBACK_MODEL", "llama-3.3-70b")
                raw = await self._call_cerebras(prompt=prompt, api_key=fallback_key, model=fallback_model)
                text = self._extract_openai_response_text(raw)
                return self._parse_refiner_json(text)

            raise RuntimeError(f"unsupported STEP1_FALLBACK_PROVIDER '{fallback_provider}'")
        except Exception as exc:
            errors.append(f"{fallback_provider} failed: {exc}")
            raise RuntimeError("Step 1 selector refinement failed after fallback: " + " | ".join(errors))

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

    async def _call_mistral(self, *, prompt: str, api_key: str, model: str) -> dict:
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

    async def _call_cerebras(self, *, prompt: str, api_key: str, model: str) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                "https://api.cerebras.ai/v1/chat/completions",
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

    def _build_prompt(self, *, objective: str, url: str, records: list[SelectorRecord]) -> str:
        raw_extracted_elements = [
            {
                "selector_id": record.selector_id,
                "tag": record.dom_tag,
                "attributes": record.dom_attributes,
                "selector": record.selector,
                "source_xpath": record.source_xpath,
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
            "Mapping constraints:\n"
            "1) Treat RAW_EXTRACTED_ELEMENTS_JSON as the only ground truth for what exists on the page.\n"
            "2) selector_id MUST be copied exactly from RAW_EXTRACTED_ELEMENTS_JSON. Never invent, rename, or transform selector_id.\n"
            "3) You may improve/stabilize the selector string for that mapped selector_id, but only for the same real element.\n"
            "4) If an item cannot be mapped to one selector_id from RAW_EXTRACTED_ELEMENTS_JSON, omit it.\n"
            "5) Never output elements that do not appear in RAW_EXTRACTED_ELEMENTS_JSON.\n\n"
            "Schema:\n"
            "{\n"
            "  \"records\": [\n"
            "    {\n"
            "      \"selector_id\": \"must exactly match a selector_id from RAW_EXTRACTED_ELEMENTS_JSON\",\n"
            "      \"selector\": \"can be original or a stabilized selector for that same mapped element\",\n"
            "      \"kind\": \"button|link|input|textarea|select|form|search\",\n"
            "      \"llm_role\": \"human readable role\",\n"
            "      \"is_fragile\": true or false,\n"
            "      \"suggested_selector\": \"stable alternative selector or null\"\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"Page URL: {url}\n"
            f"Objective: {objective}\n"
            "RAW_EXTRACTED_ELEMENTS_JSON:\n"
            + json.dumps(raw_extracted_elements, ensure_ascii=False, indent=2)
        )

    @staticmethod
    def _extract_openai_response_text(raw: dict) -> str:
        try:
            text = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Fallback LLM returned invalid response shape: {exc}") from exc
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Fallback LLM did not return JSON text")
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
