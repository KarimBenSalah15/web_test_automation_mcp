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
        self._model = model or os.getenv("STEP2_GENERATOR_MODEL", os.getenv("STEP2_MODEL", "qwen-3-235b"))
        self._timeout_seconds = timeout

    async def generate(self, *, objective: str, selector_map: SelectorMap) -> dict[str, Any]:
        api_key = os.getenv("CEREBRAS_API_KEY")
        if not api_key:
            raise ValueError("CEREBRAS_API_KEY not set in environment")

        prompt = self._build_prompt(objective=objective, selector_map=selector_map)
        raw = await self._call_cerebras(prompt=prompt, api_key=api_key)
        text = self._extract_response_text(raw)
        return self._parse_generation_json(text)

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

        return (
            "You are an expert QA planner. Generate realistic executable browser test cases from scratch.\n"
            "Use ONLY selector_id values from the provided selector map. Never invent selector_id.\n"
            "Return STRICT JSON only (no markdown).\n\n"
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
            '          "selector_id": "str or null",\n'
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


class UnimplementedStep2Generator:
    async def run(
        self,
        *,
        objective: str,
        extraction: SelectorMapExtractionResult,
    ) -> TestCaseGenerationResult:
        raise NotImplementedError("Step 2 generator not implemented yet")
