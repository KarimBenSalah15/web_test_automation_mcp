from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self, api_key: str, model: str, timeout_seconds: int = 30) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.groq.com/openai/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def generate_test_plan(self, prompt: str) -> dict[str, Any]:
        system_prompt = (
            "You are a web test planning assistant. Return strict JSON only with keys: "
            "objective (string), success_criteria (array[string]), steps (array[object]). "
            "Use action only from this list: navigate, click, type, press, wait, query. "
            "Rules: navigate requires a non-null url; click requires a non-null selector; "
            "type requires non-null selector and value; press uses value as key name like Enter; "
            "wait should not use click as wait_event. "
            "Be site-agnostic: do not hardcode one specific website behavior. "
            "Prefer semantic selectors (text labels, roles, placeholders) over brittle CSS paths. "
            "For search intents on any site, usually plan: navigate, type in search field, press Enter. "
            "Each step has: action (string), selector (string|null), value (string|null), "
            "url (string|null), wait_event (string|null), expected (string|null)."
        )

        payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            logger.info(f"Groq response status: {response.status_code}")
            if response.status_code == 400:
                logger.warning(f"Groq 400 error: {response.text[:500]}")
                fallback_payload = dict(payload)
                fallback_payload.pop("response_format", None)
                logger.info("Retrying Groq without response_format field")
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=fallback_payload,
                )
                logger.info(f"Groq fallback response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        return self._parse_json_content(content)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def decide_next_action(
        self,
        objective: str,
        current_state: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """LLM inspects current DOM state and decides the next action."""
        system_prompt = (
            "You are an autonomous web testing agent using Chrome DevTools MCP. "
            "Analyze the current browser state (URL, DOM structure, console) and decide the NEXT SINGLE action. "
            "Return strict JSON with: action (navigate|click|type|press|wait|done), selector (string|null), "
            "value (string|null), url (string|null), reasoning (string explaining why this action). "
            "Use 'done' action when objective is fully achieved. "
            "Inspect the DOM structure carefully to find the best selector (prefer semantic: role, aria-label, text). "
            "If previous action failed, analyze why and adjust your selector/strategy."
        )

        dom_summary = self._summarize_dom(current_state.get("dom", {}))
        url = current_state.get("url", "unknown")
        console_errors = current_state.get("console_errors", [])
        last_action = history[-1] if history else None

        user_message = (
            f"Objective: {objective}\n\n"
            f"Current URL: {url}\n\n"
            f"DOM Structure:\n{dom_summary}\n\n"
        )

        if console_errors:
            user_message += f"Console Errors: {console_errors[:3]}\n\n"

        if last_action:
            user_message += (
                f"Last Action: {last_action.get('action', {})}\n"
                f"Result: {'Success' if last_action.get('result', {}).get('success') else 'Failed'}\n\n"
            )

        user_message += "Decide the NEXT action to progress toward the objective."

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.status_code == 400:
                fallback_payload = dict(payload)
                fallback_payload.pop("response_format", None)
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=fallback_payload,
                )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        return self._parse_json_content(content)

    @staticmethod
    def _summarize_dom(dom: Any) -> str:
        """Extract meaningful DOM structure for LLM analysis."""
        if isinstance(dom, dict):
            content = dom.get("content", [])
            if isinstance(content, list):
                text_parts = []
                for chunk in content:
                    if isinstance(chunk, dict) and chunk.get("type") == "text":
                        text_parts.append(str(chunk.get("text", "")))
                full_text = "\n".join(text_parts)
                lines = [line.strip() for line in full_text.splitlines() if line.strip()]
                return "\n".join(lines[:150])  # Limit to first 150 lines
        return str(dom)[:3000]  # Fallback

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if not match:
                raise ValueError("LLM did not return JSON content")
            return json.loads(match.group(0))
