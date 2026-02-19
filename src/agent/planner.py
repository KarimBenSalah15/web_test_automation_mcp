from __future__ import annotations

from typing import Any

from src.llm.groq_client import GroqClient


class AgentPlanner:
    def __init__(self, groq_client: GroqClient) -> None:
        self.groq_client = groq_client

    async def plan(self, prompt: str) -> dict[str, Any]:
        raw_plan = await self.groq_client.generate_test_plan(prompt)
        return self._normalize_plan(raw_plan, prompt)

    @staticmethod
    def _normalize_plan(plan: dict[str, Any], prompt: str) -> dict[str, Any]:
        objective = str(plan.get("objective") or prompt).strip()
        criteria = plan.get("success_criteria")
        if not isinstance(criteria, list) or not criteria:
            criteria = ["Main objective completed"]

        steps = plan.get("steps")
        if not isinstance(steps, list):
            steps = []

        normalized_steps: list[dict[str, Any]] = []
        for raw in steps:
            if not isinstance(raw, dict):
                continue

            action = str(raw.get("action") or "").strip().lower()
            if action == "open":
                action = "navigate"
            if action in {"press_key", "key", "keypress"}:
                action = "press"
            if action == "fill":
                action = "type"

            step = {
                "action": action,
                "selector": raw.get("selector"),
                "value": raw.get("value"),
                "url": raw.get("url"),
                "wait_event": raw.get("wait_event"),
                "expected": raw.get("expected"),
            }

            if step["action"] == "navigate" and not step["url"]:
                if step["selector"]:
                    step["action"] = "click"
                else:
                    step["action"] = "wait"
            if step["action"] == "press" and not step["value"]:
                step["value"] = "Enter"
            if step["action"] == "wait" and step["wait_event"] == "click":
                step["wait_event"] = None

            normalized_steps.append(step)

        if not normalized_steps:
            normalized_steps = [
                {
                    "action": "query",
                    "selector": "body",
                    "value": None,
                    "url": None,
                    "wait_event": None,
                    "expected": "Page state captured",
                }
            ]

        return {
            "objective": objective,
            "success_criteria": criteria,
            "steps": normalized_steps,
        }
