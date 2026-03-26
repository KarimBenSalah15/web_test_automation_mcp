# Generator module: Generate test cases from selector map using dual-LLM flow.
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from src.step1_extract.models import SelectorMap
from src.step1_extract.models import SelectorMapExtractionResult
from src.step2_generate.models import (
    TestActionType,
    TestCase,
    TestCaseBundle,
    TestCaseGenerationResult,
    TestStep,
)
from src.step2_generate.test_case_refiner import TestCaseRefiner
from src.step2_generate.validator import SelectorWhitelistValidator


class CerebrasTestCaseGenerator:
    """LLM A: Generate executable test cases from Step 1 selector map using Cerebras."""

    def __init__(self, *, model: str | None = None, timeout: float = 30.0):
        self._model = model or os.getenv("STEP2_GENERATOR_MODEL", os.getenv("STEP2_MODEL", "zai-glm-4.7"))
        self._timeout_seconds = timeout

    async def generate(self, *, objective: str, selector_map: SelectorMap) -> dict[str, Any]:
        prompt = self._build_prompt(objective=objective, selector_map=selector_map)
        errors: list[str] = []

        primary_key = os.getenv("CEREBRAS_API_KEY", "").strip()
        if primary_key:
            try:
                raw = await self._call_cerebras(prompt=prompt, api_key=primary_key)
                text = self._extract_response_text(raw)
                return self._parse_generation_json(text)
            except Exception as exc:
                errors.append(f"cerebras failed: {exc}")
        else:
            errors.append("cerebras skipped: missing CEREBRAS_API_KEY")

        fallback_key = os.getenv("MISTRAL_API_KEY", "").strip()
        if not fallback_key:
            errors.append("mistral skipped: missing MISTRAL_API_KEY")
            raise RuntimeError("Step 2 generation failed after fallback: " + " | ".join(errors))

        fallback_model = os.getenv("STEP2_GENERATOR_FALLBACK_MODEL", "mistral-large-latest")
        try:
            raw = await self._call_mistral(prompt=prompt, api_key=fallback_key, model=fallback_model)
            text = self._extract_response_text(raw)
            return self._parse_generation_json(text)
        except Exception as exc:
            errors.append(f"mistral failed: {exc}")
            raise RuntimeError("Step 2 generation failed after fallback: " + " | ".join(errors))

    def _build_prompt(self, *, objective: str, selector_map: SelectorMap) -> str:
        selector_payload = [
            {
                "selector_id": record.selector_id,
                "selector": record.selector,
                "kind": record.kind.value,
                "llm_role": record.llm_role,
                "label": record.label,
                "placeholder": record.placeholder,
                "text": record.text,
                "is_fragile": record.is_fragile,
                "suggested_selector": record.suggested_selector,
            }
            for record in selector_map.records
        ]

        valid_selector_ids = [record.selector_id for record in selector_map.records]

        return (
            "You are an expert QA planner. Generate realistic executable browser test cases from scratch.\n"
            "CRITICAL RULES - VIOLATIONS WILL CAUSE FAILURE:\n"
            "1. Use ONLY selector_id values from the provided VALID_SELECTOR_IDS list below.\n"
            "2. Every single selector_id in every test step MUST be copied exactly from the VALID_SELECTOR_IDS list.\n"
            "3. It is STRICTLY FORBIDDEN to invent, modify, or hallucinate any selector_id.\n"
            "4. Do not add prefixes, suffixes, or variations to selector_ids.\n"
            "5. If a test step uses a selector, the selector_id MUST exist in VALID_SELECTOR_IDS.\n"
            "6. Do not use any selector_id that is not in the list, even if it seems logical.\n"
            "Return STRICT JSON only (no markdown).\n\n"
            f"VALID_SELECTOR_IDS (ONLY these are allowed):\n{json.dumps(valid_selector_ids)}\n\n"
            f"OBJECTIVE:\n{objective}\n\n"
            f"SELECTOR_MAP_JSON:\n{json.dumps(selector_payload, ensure_ascii=True)}\n\n"
            "OUTPUT_SCHEMA:\n"
            "{\n"
            '  "cases": [\n'
            "    {\n"
            '      "test_id": "str",\n'
            '      "objective": "str",\n'
            '      "steps": [\n'
            "        {\n"
            '          "step_id": "str",\n'
            '          "action": "click|type|press|wait|assert_text|assert_visible",\n'
            '          "selector_id": "str or null (MUST be from VALID_SELECTOR_IDS if not null)",\n'
            '          "value": "str or null",\n'
            '          "timeout_ms": 10000,\n'
            '          "notes": "str or null"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n"
        )

    async def _call_cerebras(self, *, prompt: str, api_key: str) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                "https://api.cerebras.ai/v1/chat/completions",
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

    def _extract_response_text(self, raw_response: dict) -> str:
        try:
            return raw_response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Failed to extract text from Cerebras response: {exc}")

    def _parse_generation_json(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(line for line in lines[1:-1] if not line.startswith("```"))

        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected root JSON object, got {type(payload).__name__}")
        cases = payload.get("cases")
        if not isinstance(cases, list):
            raise ValueError("Generated payload must include a 'cases' list")
        return payload


class Step2Generator:
    """Generate test cases from selector map using dual-LLM flow."""

    def __init__(
        self,
        *,
        generator_llm: CerebrasTestCaseGenerator | None = None,
        refiner: TestCaseRefiner | None = None,
        validator: SelectorWhitelistValidator | None = None,
    ):
        """Initialize Step 2 with LLM A (generation), LLM B (refinement), and final validator."""
        self._generator_llm = generator_llm or CerebrasTestCaseGenerator()
        self._refiner = refiner or TestCaseRefiner()
        self._validator = validator or SelectorWhitelistValidator()

    async def run(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
    ) -> TestCaseGenerationResult:
        # Step 1 (LLM A): generate test cases from scratch from Step 1 output.
        generated_payload = await self._generator_llm.generate(
            objective=objective,
            selector_map=extraction.selector_map,
        )

        # Pre-whitelist check: compare selector_ids provided vs returned
        self._check_selector_id_consistency(
            valid_ids=extraction.selector_map.selector_ids(),
            generated_payload=generated_payload,
        )

        # Step 2 (LLM B): validate/enrich generated cases.
        refined_payload = await self._refiner.refine(
            objective=objective,
            selector_map=extraction.selector_map,
            generated_payload=generated_payload,
        )

        # Step 3: deterministic safety net on selector IDs.
        rebuilt = self._rebuild_result_from_payload(refined_payload)
        return self._validator.validate(
            result=rebuilt,
            selector_map=extraction.selector_map,
        )

    def _rebuild_result_from_payload(
        self,
        payload: dict,
    ) -> TestCaseGenerationResult:
        """Convert LLM JSON payload to typed TestCaseGenerationResult."""
        cases = []

        for case_data in payload.get("cases", []):
            steps = []
            for step_data in case_data.get("steps", []):
                steps.append(
                    TestStep(
                        step_id=step_data["step_id"],
                        action=TestActionType(step_data["action"]),
                        selector_id=step_data.get("selector_id"),
                        value=step_data.get("value"),
                        timeout_ms=step_data.get("timeout_ms", 10000),
                        notes=step_data.get("notes"),
                    )
                )

            cases.append(
                TestCase(
                    test_id=case_data["test_id"],
                    objective=case_data["objective"],
                    steps=steps,
                )
            )

        return TestCaseGenerationResult(
            bundle=TestCaseBundle(cases=cases),
            validation_errors=[],
        )

    def _check_selector_id_consistency(self, *, valid_ids: set[str], generated_payload: dict) -> None:
        """
        Check that all selector_ids used in generated test cases are in the valid set.
        Print diagnostics showing provided vs returned selector_ids.
        """
        returned_ids: set[str] = set()

        for case_data in generated_payload.get("cases", []):
            for step_data in case_data.get("steps", []):
                selector_id = step_data.get("selector_id")
                if selector_id:
                    returned_ids.add(selector_id)

        provided_sorted = sorted(valid_ids)
        returned_sorted = sorted(returned_ids)

        print(f"\n--- Pre-Whitelist Selector ID Check ---")
        print(f"Provided selector_ids ({len(valid_ids)}): {provided_sorted}")
        print(f"Returned selector_ids ({len(returned_ids)}): {returned_sorted}")

        invalid_ids = returned_ids - valid_ids
        if invalid_ids:
            invalid_sorted = sorted(invalid_ids)
            print(f"WARNING: {len(invalid_sorted)} unknown selector_ids found in LLM response: {invalid_sorted}")
            print("The LLM hallucinated selector_ids not in the provided map. This will fail validation.")
        
        unused_ids = valid_ids - returned_ids
        if unused_ids:
            unused_sorted = sorted(unused_ids)
            print(f"INFO: {len(unused_sorted)} provided selector_ids were not used: {unused_sorted}")
        
        print(f"--- End Selector ID Check ---\n")


class UnimplementedStep2Generator:
    async def run(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
    ) -> TestCaseGenerationResult:
        raise NotImplementedError("Step 2 generator not implemented yet")
