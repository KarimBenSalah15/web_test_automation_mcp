from __future__ import annotations

import asyncio
import re
from collections import deque
from pathlib import Path
from typing import Any

from src.agent.memory import AgentMemory
from src.agent.policy import to_browser_action
from src.agent.retry import should_retry
from src.browser.devtools_adapter import DevToolsAdapter
from src.browser.dom_utils import DomSnapshot, DomDiffer
from src.browser.observe import Observation
from src.llm.groq_client import GroqClient


class AgentLoop:
    def __init__(
        self,
        adapter: DevToolsAdapter,
        groq_client: GroqClient,
        max_steps: int = 20,
        step_retry_limit: int = 2,
        artifacts_dir: str = "artifacts",
        verbose: bool = False,
    ) -> None:
        self.adapter = adapter
        self.groq_client = groq_client
        self.max_steps = max_steps
        self.step_retry_limit = step_retry_limit
        self.verbose = verbose
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # DOM tracking for Fail-Fast heuristics
        self.recent_dom_snapshots: deque[DomSnapshot] = deque(maxlen=5)
        self.consecutive_unchanged_count = 0

    async def run(self, objective: str) -> AgentMemory:
        """Agentic loop: LLM inspects DOM and decides actions dynamically."""
        memory = AgentMemory(prompt=objective, test_plan={"objective": objective})
        step_idx = 0

        while step_idx < self.max_steps:
            print(f"\n⏳ Step {step_idx + 1}/{self.max_steps}")
            memory.step_index = step_idx

            # Observe current browser state
            obs = await self._observe(step_idx)
            current_state = await self._build_state(obs)
            
            # Create DOM snapshot BEFORE action
            dom_snapshot_before = DomSnapshot(obs.accessibility)
            self.recent_dom_snapshots.append(dom_snapshot_before)

            # LLM decides next action based on current DOM
            try:
                decision = await self.groq_client.decide_next_action(
                    objective=objective,
                    current_state=current_state,
                    history=memory.history,
                    dom_unchanged_count=self.consecutive_unchanged_count,
                )
            except Exception as exc:
                print(f"   ❌ LLM Error: {exc}")
                memory.last_error = f"LLM decision error: {exc}"
                break

            action_type = str(decision.get("action", "")).strip().lower()
            reasoning = decision.get("reasoning", "No reasoning provided")
            
            print(f"   Action: {action_type}")
            print(f"   Reasoning: {reasoning}")
            
            if self.verbose:
                selector = decision.get("selector")
                value = decision.get("value")
                url = decision.get("url")
                if selector:
                    print(f"   Selector: {selector}")
                if value:
                    print(f"   Value: {value}")
                if url:
                    print(f"   URL: {url}")

            # Check if objective is done
            if action_type == "done":
                print("   ✅ PASSED")
                memory.success = True
                break

            # Convert LLM decision to browser action
            browser_action = self._decision_to_action(decision)

            # Execute action with retry
            attempt = 0
            result = None
            while attempt < self.step_retry_limit:
                attempt += 1
                if self.verbose and self.step_retry_limit > 1:
                    print(f"   Attempt {attempt}/{self.step_retry_limit}...")
                result = await self._execute_action(browser_action)
                has_error = not result.get("success", False)
                tools_used = result.get("tools_used", [])

                memory.push(
                    {
                        "step": step_idx,
                        "attempt": attempt,
                        "action": decision,
                        "result": result,
                        "observation": {
                            "console": obs.console,
                            "console_has_error": obs.has_errors(),
                        },
                    }
                )

                if not has_error:
                    tools_str = ", ".join(tools_used) if tools_used else "none"
                    print(f"   ✅ PASSED | Tools: {tools_str}")
                    break

                if attempt >= self.step_retry_limit:
                    error_msg = result.get("reason") or result.get("error") or "Unknown error"
                    tools_str = ", ".join(tools_used) if tools_used else "none"
                    print(f"   ❌ FAILED after {attempt} attempts: {error_msg} | Tools: {tools_str}")
                    # Don't break - let LLM see the failure and adjust next action
            
            # Check for DOM changes (Fail-Fast heuristics)
            try:
                obs_after = await self._observe(step_idx)
                dom_snapshot_after = DomSnapshot(obs_after.accessibility)
                differ = DomDiffer(dom_snapshot_before, dom_snapshot_after)
                
                if not differ.has_changed():
                    self.consecutive_unchanged_count += 1
                    if self.verbose:
                        print(f"   ⚠️ DOM unchanged ({self.consecutive_unchanged_count}/3)")
                else:
                    self.consecutive_unchanged_count = 0
                
                # Store result with DOM change info
                if memory.history:
                    memory.history[-1]["dom_changed"] = differ.has_changed()
            except Exception:
                # If snapshot fails, reset unchanged counter to be safe
                self.consecutive_unchanged_count = 0

            step_idx += 1

        if step_idx >= self.max_steps:
            memory.last_error = "Max steps reached"

        memory.success = memory.last_error is None and memory.success
        return memory

    def _decision_to_action(self, decision: dict[str, Any]) -> Any:
        """Convert LLM decision to BrowserAction."""
        action_dict = {
            "action": decision.get("action", "wait"),
            "selector": decision.get("selector"),
            "value": decision.get("value"),
            "url": decision.get("url"),
            "wait_event": decision.get("wait_event"),
            "expected": decision.get("reasoning"),
        }
        return to_browser_action(action_dict)

    async def _build_state(self, obs: Observation) -> dict[str, Any]:
        """Build current state for LLM analysis."""
        url = "unknown"
        try:
            # Try to extract URL from accessibility tree or DOM
            if isinstance(obs.accessibility, dict):
                url_match = re.search(
                    r"https?://[^\s]+",
                    str(obs.accessibility),
                    flags=re.IGNORECASE,
                )
                if url_match:
                    url = url_match.group(0)
        except Exception:
            pass

        console_errors = []
        if isinstance(obs.console, dict):
            content = obs.console.get("content", [])
            for chunk in content:
                if isinstance(chunk, dict) and "error" in str(chunk).lower():
                    console_errors.append(str(chunk.get("text", ""))[:200])

        return {
            "url": url,
            "dom": obs.accessibility,  # Accessibility tree is more structured
            "console_errors": console_errors,
        }

    async def _execute_action(self, action: Any) -> dict[str, Any]:
        try:
            if action.action_type in {"open", "navigate"} and action.url:
                raw = await self.adapter.open_url(action.url)
            elif action.action_type == "click" and action.selector:
                raw = await self.adapter.click(action.selector)
                # Self-Repair: Get alternatives if click fails
                if isinstance(raw, dict) and raw.get("isError") is True:
                    alternatives = await self.adapter.get_clickable_alternatives(action.selector)
                    if alternatives:
                        raw["suggested_alternatives"] = alternatives
            elif action.action_type == "type" and action.selector:
                raw = await self.adapter.type_text(action.selector, action.value or "")
            elif action.action_type == "press":
                raw = await self.adapter.press_key(action.value or "Enter")
            elif action.action_type in {"wait", "wait_for_text"}:
                if action.wait_event:
                    raw = await self.adapter.wait_for(action.wait_event, action.timeout_ms)
                    if isinstance(raw, dict) and raw.get("isError") is True:
                        error_text = self._extract_mcp_error(raw)
                        if self._looks_like_timeout_error(error_text):
                            fallback = await self.adapter.smart_wait_fallback(action.wait_event)
                            if isinstance(fallback, dict) and fallback.get("ok") is True:
                                raw = {
                                    "smart_fallback": fallback,
                                    "source": "wait_for_timeout_recovered",
                                }
                else:
                    delay_ms = int(action.value or "1500")
                    await asyncio.sleep(max(delay_ms, 0) / 1000)
                    raw = {"slept_ms": delay_ms}
            elif action.action_type == "query":
                raw = await self.adapter.query_dom(action.selector or "body")
            else:
                tools_used = self.adapter.get_tools_used()
                return {"success": False, "reason": f"Unsupported action: {action.action_type}", "tools_used": tools_used}

            # Get tools used in this action
            tools_used = self.adapter.get_tools_used()

            if isinstance(raw, dict):
                fallback = raw.get("smart_fallback")
                if isinstance(fallback, dict) and fallback.get("ok") is True:
                    return {"success": True, "raw": raw, "tools_used": tools_used}

            if isinstance(raw, dict) and raw.get("isError") is True:
                return {
                    "success": False,
                    "reason": self._extract_mcp_error(raw),
                    "raw": raw,
                    "tools_used": tools_used,
                }
            business_failure_reason = self._extract_business_failure(raw)
            if business_failure_reason:
                return {
                    "success": False,
                    "reason": business_failure_reason,
                    "raw": raw,
                    "tools_used": tools_used,
                }
            return {"success": True, "raw": raw, "tools_used": tools_used}
        except Exception as exc:
            tools_used = self.adapter.get_tools_used()
            error_msg = f"{type(exc).__name__}: {str(exc)}" if str(exc) else type(exc).__name__
            return {"success": False, "reason": error_msg, "tools_used": tools_used}

    @staticmethod
    def _extract_mcp_error(raw: dict[str, Any]) -> str:
        content = raw.get("content")
        if isinstance(content, list):
            for chunk in content:
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    text = str(chunk.get("text", "")).strip()
                    if text:
                        return text
        return "MCP tool returned an error"

    @classmethod
    def _extract_business_failure(cls, raw: Any) -> str | None:
        reason = cls._extract_failure_reason(raw)
        if reason:
            return reason

        if cls._contains_negative_signal(raw):
            return "Action failed based on tool result"
        return None

    @classmethod
    def _extract_failure_reason(cls, raw: Any) -> str | None:
        if isinstance(raw, dict):
            for key in ("reason", "error", "message", "details"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip() and cls._looks_like_failure_text(value):
                    return value.strip()

            content = raw.get("content")
            if isinstance(content, list):
                for chunk in content:
                    if isinstance(chunk, dict) and chunk.get("type") == "text":
                        text = str(chunk.get("text", "")).strip()
                        if text and cls._looks_like_failure_text(text):
                            return text

            for value in raw.values():
                nested = cls._extract_failure_reason(value)
                if nested:
                    return nested

        if isinstance(raw, list):
            for item in raw:
                nested = cls._extract_failure_reason(item)
                if nested:
                    return nested

        return None

    @classmethod
    def _contains_negative_signal(cls, raw: Any) -> bool:
        if isinstance(raw, dict):
            for key in ("ok", "success", "status"):
                if key in raw and isinstance(raw.get(key), bool) and raw.get(key) is False:
                    return True
            return any(cls._contains_negative_signal(value) for value in raw.values())

        if isinstance(raw, list):
            return any(cls._contains_negative_signal(item) for item in raw)

        return False

    @staticmethod
    def _looks_like_failure_text(text: str) -> bool:
        return bool(
            re.search(
                r"\b(error|failed|failure|timeout|no\s+clickable|no\s+editable|could\s+not\s+resolve|not\s+found)\b",
                text,
                flags=re.IGNORECASE,
            )
        )

    @staticmethod
    def _looks_like_timeout_error(text: str) -> bool:
        return bool(re.search(r"\b(timed?\s*out|timeout)\b", text, flags=re.IGNORECASE))

    async def _observe(self, step_idx: int) -> Observation:
        screenshot_path = str(self.artifacts_dir / f"step_{step_idx}.png")
        screenshot_file_exists = False

        try:
            await asyncio.wait_for(self.adapter.screenshot(screenshot_path), timeout=10)
            screenshot_file_exists = Path(screenshot_path).exists()
        except Exception:
            screenshot_file_exists = False

        try:
            dom = await asyncio.wait_for(self.adapter.query_dom("body"), timeout=8)
        except Exception as exc:
            dom = {"error": str(exc)}

        try:
            console = await asyncio.wait_for(self.adapter.read_console(), timeout=8)
        except Exception as exc:
            console = [{"error": str(exc)}]

        try:
            accessibility = await asyncio.wait_for(self.adapter.accessibility_tree(), timeout=8)
        except Exception as exc:
            accessibility = {"error": str(exc)}

        return Observation(dom=dom, console=console, accessibility=accessibility)