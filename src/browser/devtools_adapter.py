from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from src.mcp_client.session import McpSession


class DevToolsAdapter:
    def __init__(self, session: McpSession) -> None:
        self.session = session
        self._last_action_tools: list[str] = []

    async def _call_and_track(self, tool_name: str, params: dict[str, Any]) -> Any:
        """Call a tool and automatically track it."""
        self._called_tool(tool_name)  # Track BEFORE calling so it's recorded even if call fails
        result = await self.session.call_tool(tool_name, params)
        return result

    def _called_tool(self, tool_name: str) -> None:
        """Track a tool call for the current action."""
        if tool_name not in self._last_action_tools:
            self._last_action_tools.append(tool_name)

    def get_tools_used(self) -> list[str]:
        """Get and reset tools used in the last action."""
        tools = self._last_action_tools.copy()
        self._last_action_tools.clear()
        return tools

    async def open_url(self, url: str) -> Any:
        self._last_action_tools.clear()
        raw = await self._call_and_track("navigate_page", {"url": url})
        if isinstance(raw, dict) and raw.get("isError") is True:
            return raw

        readiness = await self.wait_until_page_ready()
        if isinstance(readiness, dict) and readiness.get("ok") is False:
            return readiness
        return {"navigate": raw, "page_ready": readiness}

    async def query_dom(self, selector: str) -> Any:
        self._last_action_tools.clear()
        return await self._call_and_track("take_snapshot", {})

    async def click(self, selector: str) -> Any:
        self._last_action_tools.clear()
        selector_json = json.dumps(selector)
        script = (
            "() => {"
            f"const target = {selector_json};"
            "const normalized = String(target || '').trim();"
            "if (!normalized) return {ok:false, reason:'empty selector'};"
            "const looksLikeCss = /[#.\\[\\]>:+~]/.test(normalized) || /^[a-z][a-z0-9_-]*(\\s|$)/i.test(normalized);"
            "const clickableSelector = 'button, a, [role=\"button\"], input[type=\"submit\"], input[type=\"button\"], summary';"
            "const asClickable = (node) => {"
            "if (!node) return null;"
            "if (node.matches && node.matches(clickableSelector)) return node;"
            "if (node.closest) { const parent = node.closest(clickableSelector); if (parent) return parent; }"
            "if (node.querySelector) { const child = node.querySelector(clickableSelector); if (child) return child; }"
            "return null;"
            "};"
            "const isVisible = (node) => {"
            "if (!node) return false;"
            "const rect = node.getBoundingClientRect();"
            "if (!rect || rect.width <= 1 || rect.height <= 1) return false;"
            "const style = window.getComputedStyle(node);"
            "if (!style || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;"
            "return true;"
            "};"
            "const scoreNode = (node) => {"
            "if (!node) return -1e9;"
            "const rect = node.getBoundingClientRect();"
            "const cx = rect.left + rect.width / 2;"
            "const cy = rect.top + rect.height / 2;"
            "const centerDist = Math.hypot(cx - window.innerWidth / 2, cy - window.innerHeight / 2);"
            "let score = -centerDist / 25;"
            "if (node.tagName === 'A') score += 20;"
            "const href = String((node.getAttribute && node.getAttribute('href')) || '').trim().toLowerCase();"
            "if (href) score += 8;"
            "if (href.startsWith('#') || href.startsWith('javascript:')) score -= 80;"
            "if (href.includes('/watch') || href.includes('watch?v=')) score += 70;"
            "if (href.includes('results?search_query=')) score -= 35;"
            "const text = (node.innerText || node.textContent || '').trim();"
            "if (text.length >= 8) score += 10;"
            "if (node.closest('main, article, [role=\"main\"], ytd-two-column-search-results-renderer, ytd-video-renderer, ytd-rich-item-renderer')) score += 35;"
            "if (node.closest('nav, aside, header, [role=\"navigation\"], #guide, [id*=\"guide\"], [class*=\"sidebar\"]')) score -= 120;"
            "return score;"
            "};"
            "const chooseBest = (nodes) => {"
            "const dedup = Array.from(new Set(nodes.filter(Boolean)));"
            "const visible = dedup.filter(isVisible);"
            "if (!visible.length) return null;"
            "let best = visible[0];"
            "let bestScore = scoreNode(best);"
            "for (const node of visible.slice(1)) {"
            "const score = scoreNode(node);"
            "if (score > bestScore) { best = node; bestScore = score; }"
            "}"
            "return best;"
            "};"
            "let el = null;"
            "let matched = [];"
            "try { matched = Array.from(document.querySelectorAll(normalized)); } catch (_) { matched = []; }"
            "if (matched.length) {"
            "const clickableCandidates = matched.map(asClickable).filter(Boolean);"
            "el = chooseBest(clickableCandidates);"
            "}"
            "if (!el && !looksLikeCss) {"
            "const needle = normalized.toLowerCase();"
            "const candidates = Array.from(document.querySelectorAll(clickableSelector));"
            "const matchedByText = candidates.filter((node) => {"
            "const text = (node.innerText || node.textContent || node.getAttribute('aria-label') || node.getAttribute('title') || node.value || '').toLowerCase();"
            "return text.includes(needle);"
            "});"
            "el = chooseBest(matchedByText);"
            "}"
            "if (!el && /heading/i.test(normalized)) {"
            "const mainRoot = document.querySelector('main, [role=\"main\"], #contents') || document;"
            "const contentLinks = Array.from(mainRoot.querySelectorAll('a[href], button, [role=\"button\"]'));"
            "const strong = contentLinks.filter((node) => {"
            "const text = (node.innerText || node.textContent || '').trim();"
            "const href = String((node.getAttribute && node.getAttribute('href')) || '').trim().toLowerCase();"
            "if (text.length < 8) return false;"
            "if (!href) return true;"
            "if (href.startsWith('#') || href.startsWith('javascript:')) return false;"
            "return true;"
            "});"
            "el = chooseBest(strong.map(asClickable));"
            "}"
            "if (!el && /yt-formatted-string/i.test(normalized) && /heading/i.test(normalized)) {"
            "const ytCandidates = Array.from(document.querySelectorAll('a#video-title, ytd-video-renderer a[href*=\"/watch\"], ytd-rich-item-renderer a[href*=\"/watch\"], ytd-rich-grid-media a[href*=\"/watch\"]'));"
            "el = chooseBest(ytCandidates.map(asClickable));"
            "}"
            "if (!el) return {ok:false, reason:'no clickable element found'};"
            "el.scrollIntoView({block:'center', inline:'center'});"
            "el.click();"
            "return {ok:true, tag: String(el.tagName || '').toLowerCase(), text: (el.innerText || el.textContent || '').trim().slice(0, 120)};"
            "}"
        )
        deadline = time.monotonic() + 6
        script_raw: Any = None

        while time.monotonic() <= deadline:
            script_raw = await self._call_and_track("evaluate_script", {"function": script})
            if not isinstance(script_raw, dict):
                return script_raw

            if script_raw.get("isError") is not True and self._script_result_ok(script_raw):
                return script_raw

            if not self._is_transient_click_miss(script_raw):
                break
            await asyncio.sleep(0.25)

        uid = await self._resolve_uid(selector, preferred_roles=("button", "link"))
        result = await self._call_and_track("click", {"uid": uid})
        return result

    async def type_text(self, selector: str, text: str) -> Any:
        self._last_action_tools.clear()
        selector_json = json.dumps(selector)
        text_json = json.dumps(text)
        script = (
            "() => {"
            f"const selector = {selector_json};"
            f"const value = {text_json};"
            "const normalized = String(selector || '').trim();"
            "const roleMatch = /^role\\s*[:=]\\s*([a-z0-9_-]+)$/i.exec(normalized);"
            "let el = null;"
            "if (normalized) {"
            "try { el = document.querySelector(normalized); } catch (_) {}"
            "}"
            "const interactive = Array.from(document.querySelectorAll('textarea, input[type=\"search\"], input[type=\"text\"], input:not([type]), input[name=\"q\"], textarea[name=\"q\"], [contenteditable=\"true\"], [role=\"textbox\"], [role=\"searchbox\"]'));"
            "if (!el && roleMatch) {"
            "const role = roleMatch[1].toLowerCase();"
            "el = Array.from(document.querySelectorAll(`[role=\"${role}\"]`)).find(Boolean) || null;"
            "}"
            "if (!el && normalized) {"
            "const needle = normalized.toLowerCase();"
            "el = interactive.find((node) => {"
            "const textBlob = ["
            "node.getAttribute('name'),"
            "node.getAttribute('placeholder'),"
            "node.getAttribute('aria-label'),"
            "node.getAttribute('title'),"
            "node.id,"
            "node.innerText,"
            "node.textContent"
            "].filter(Boolean).join(' ').toLowerCase();"
            "return textBlob.includes(needle);"
            "});"
            "}"
            "if (!el) {"
            "el = interactive.find((node) => !node.disabled && node.getAttribute('type') !== 'hidden') || null;"
            "}"
            "if (!el) return {ok:false, reason:'No editable element found'};"
            "el.focus();"
            "if ('value' in el) { el.value = value; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }"
            "else { el.textContent = value; }"
            "return {ok:true};"
            "}"
        )
        script_raw = await self._call_and_track("evaluate_script", {"function": script})
        if not isinstance(script_raw, dict):
            return script_raw
        if script_raw.get("isError") is not True and self._script_result_ok(script_raw):
            return script_raw

        uid = await self._resolve_uid(
            selector,
            preferred_roles=("searchbox", "textbox", "textarea", "input"),
        )
        result = await self._call_and_track(
            "fill",
            {
                "uid": uid,
                "value": text,
            },
        )
        return result

    async def wait_until_page_ready(self, timeout_ms: int = 6000, poll_ms: int = 200) -> dict[str, Any]:
        script = (
            "() => {"
            "const readyState = document.readyState || 'loading';"
            "const hasBody = Boolean(document.body);"
            "const href = String(window.location && window.location.href || '');"
            "return {readyState, hasBody, href};"
            "}"
        )

        deadline = time.monotonic() + max(timeout_ms, 0) / 1000
        last_state: dict[str, Any] = {"readyState": "loading", "hasBody": False, "href": ""}

        while time.monotonic() <= deadline:
            raw = await self._call_and_track("evaluate_script", {"function": script})
            if isinstance(raw, dict):
                if raw.get("isError") is True:
                    return {
                        "ok": False,
                        "reason": "evaluate_script failed while waiting for page readiness",
                        "raw": raw,
                    }
                state = self._extract_script_result_payload(raw)
                if isinstance(state, dict):
                    last_state = {
                        "readyState": str(state.get("readyState", "loading")),
                        "hasBody": bool(state.get("hasBody", False)),
                        "href": str(state.get("href", "")),
                    }
                    if last_state["hasBody"] and last_state["readyState"] in {"interactive", "complete"}:
                        return {"ok": True, **last_state}

            await asyncio.sleep(max(poll_ms, 50) / 1000)

        if last_state["hasBody"]:
            return {"ok": True, **last_state, "reason": "body detected before full readyState"}

        return {
            "ok": False,
            "reason": "Timeout waiting for page to be ready",
            **last_state,
        }

    async def wait_for(self, event: str, timeout_ms: int = 5000) -> Any:
        self._last_action_tools.clear()
        return await self._call_and_track(
            "wait_for",
            {
                "text": event,
                "timeout": timeout_ms,
            },
        )

    async def smart_wait_fallback(self, event: str) -> dict[str, Any]:
        event_text = (event or "").strip()
        lowered = event_text.lower()

        state_script = (
            "() => {"
            "const href = String(window.location && window.location.href || '');"
            "const title = String(document.title || '');"
            "const player = document.querySelector('#movie_player, ytd-player, .html5-video-player');"
            "const video = document.querySelector('video');"
            "const hasVideo = Boolean(video);"
            "const hasPlayer = Boolean(player);"
            "const videoPlaying = Boolean(video && !video.paused && !video.ended && video.readyState >= 2);"
            "const hasBody = Boolean(document.body);"
            "return {href, title, hasPlayer, hasVideo, videoPlaying, hasBody};"
            "}"
        )

        raw = await self._call_and_track("evaluate_script", {"function": state_script})
        state = self._extract_script_result_payload(raw) if isinstance(raw, dict) else None
        if not isinstance(state, dict):
            state = {}

        href = str(state.get("href", "")).lower()
        title = str(state.get("title", "")).lower()
        has_player = bool(state.get("hasPlayer", False))
        has_video = bool(state.get("hasVideo", False))
        video_playing = bool(state.get("videoPlaying", False))
        has_body = bool(state.get("hasBody", False))

        if any(token in lowered for token in ("video", "playback", "player", "lecture", "regarde", "watch")):
            is_watch_url = "youtube.com/watch" in href or "youtu.be/" in href or "/watch?" in href
            if video_playing:
                return {
                    "ok": True,
                    "reason": "Video is actively playing",
                    "event": event_text,
                    "href": href,
                }
            if is_watch_url and (has_player or has_video):
                return {
                    "ok": True,
                    "reason": "Watch page opened with video/player present",
                    "event": event_text,
                    "href": href,
                }

        snapshot_raw = await self._call_and_track("take_snapshot", {})
        snapshot_text = self._snapshot_text(snapshot_raw).lower()
        if event_text and event_text.lower() in snapshot_text:
            return {
                "ok": True,
                "reason": "wait_event text found in DOM snapshot",
                "event": event_text,
                "href": href,
            }

        if has_body and any(token in lowered for token in ("loaded", "charg", "ready", "prêt")):
            return {
                "ok": True,
                "reason": "Document body is present",
                "event": event_text,
                "href": href,
            }

        return {
            "ok": False,
            "reason": "Fallback validation did not confirm wait condition",
            "event": event_text,
            "href": href,
            "title": title,
            "hasPlayer": has_player,
            "hasVideo": has_video,
            "videoPlaying": video_playing,
        }

    async def press_key(self, key: str) -> Any:
        self._last_action_tools.clear()
        return await self._call_and_track(
            "press_key",
            {
                "key": key,
            },
        )

    async def read_console(self) -> Any:
        return await self.session.call_tool("list_console_messages", {})

    async def accessibility_tree(self) -> Any:
        return await self.session.call_tool("take_snapshot", {})

    async def screenshot(self, path: str) -> Any:
        return await self.session.call_tool(
            "take_screenshot",
            {
                "filePath": path,
                "format": "png",
            },
        )

    async def list_page_ids(self) -> list[int]:
        raw = await self.session.call_tool("list_pages", {})
        text = self._snapshot_text(raw)
        page_ids: list[int] = []
        for line in text.splitlines():
            match = re.match(r"\s*(\d+)\s*:", line)
            if match:
                page_ids.append(int(match.group(1)))
        return page_ids

    async def close_all_pages(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page_ids = await self.list_page_ids()
        for page_id in sorted(page_ids, reverse=True):
            try:
                raw = await self.session.call_tool("close_page", {"pageId": page_id})
                if isinstance(raw, dict) and raw.get("isError") is True:
                    results.append({"pageId": page_id, "success": False, "raw": raw})
                else:
                    results.append({"pageId": page_id, "success": True, "raw": raw})
            except Exception as exc:
                results.append({"pageId": page_id, "success": False, "reason": str(exc)})
        return results

    async def _resolve_uid(self, selector: str, preferred_roles: tuple[str, ...]) -> str:
        token = (selector or "").strip()
        if re.fullmatch(r"\d+_\d+", token):
            return token

        token_looks_like_css = self._looks_like_css_selector(token)

        snapshot = await self._call_and_track("take_snapshot", {})
        snapshot_text = self._snapshot_text(snapshot)
        lines = [line.strip() for line in snapshot_text.splitlines() if line.strip()]

        role_selector_match = re.fullmatch(r"role\s*[:=]\s*([a-zA-Z0-9_-]+)", token, flags=re.IGNORECASE)
        token_looks_like_role_selector = bool(re.match(r"^role\s*[:=]", token, flags=re.IGNORECASE))
        if role_selector_match:
            requested_role = role_selector_match.group(1).lower()
            uid = self._find_first_uid_by_role(lines, requested_role)
            if uid:
                return uid

        text_match = token.strip('"\'')
        if text_match and preferred_roles and not token_looks_like_css:
            for role in preferred_roles:
                uid = self._find_first_uid_by_role(lines, role, text_match=text_match)
                if uid:
                    return uid

        if not token_looks_like_css:
            for role in preferred_roles:
                uid = self._find_first_uid_by_role(lines, role)
                if uid:
                    return uid

        if text_match and re.search(r"[A-Za-zÀ-ÿ]", text_match) and not token_looks_like_role_selector and not token_looks_like_css:
            for line in lines:
                uid = self._extract_uid(line)
                if uid and text_match.lower() in line.lower():
                    return uid

        if not token_looks_like_css:
            lowered = token.lower()
            if "button" in lowered:
                uid = self._find_first_uid_by_role(lines, "button")
                if uid:
                    return uid
            if "link" in lowered:
                uid = self._find_first_uid_by_role(lines, "link")
                if uid:
                    return uid

        if token_looks_like_css:
            raise RuntimeError(f"Could not resolve MCP uid from CSS-like selector: {selector}")

        fallback_uid = self._find_first_uid(lines)
        if fallback_uid:
            return fallback_uid
        raise RuntimeError(f"Could not resolve MCP uid for selector: {selector}")

    @staticmethod
    def _looks_like_css_selector(token: str) -> bool:
        if not token:
            return False
        return bool(re.search(r"[#.\[\]>:+~]|\s", token)) or bool(re.match(r"^[a-z][a-z0-9_-]*$", token, flags=re.IGNORECASE))

    @staticmethod
    def _snapshot_text(snapshot: Any) -> str:
        if not isinstance(snapshot, dict):
            return str(snapshot)
        content = snapshot.get("content", [])
        if isinstance(content, list):
            parts: list[str] = []
            for chunk in content:
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    parts.append(str(chunk.get("text", "")))
            return "\n".join(parts)
        return str(snapshot)

    @staticmethod
    def _extract_uid(line: str) -> str | None:
        match = re.search(r"uid=(\d+_\d+)", line)
        return match.group(1) if match else None

    def _find_first_uid_by_role(self, lines: list[str], role: str, text_match: str | None = None) -> str | None:
        role_token = f" {role} "
        text = (text_match or "").lower()
        for line in lines:
            uid = self._extract_uid(line)
            lowered_line = line.lower()
            if uid and role_token in f" {lowered_line} ":
                if text and text not in lowered_line:
                    continue
                return uid
        return None

    def _find_first_uid(self, lines: list[str]) -> str | None:
        for line in lines:
            uid = self._extract_uid(line)
            if uid:
                return uid
        return None

    @staticmethod
    def _script_result_ok(raw: dict[str, Any]) -> bool:
        if "ok" in raw:
            return bool(raw.get("ok"))
        if "success" in raw:
            return bool(raw.get("success"))
        if "status" in raw and isinstance(raw.get("status"), bool):
            return bool(raw.get("status"))
        text = DevToolsAdapter._flatten_text(raw).lower()
        if '"ok":false' in text or '"success":false' in text:
            return False
        if '"ok":true' in text or '"success":true' in text:
            return True
        return True

    @classmethod
    def _extract_script_result_payload(cls, raw: dict[str, Any]) -> dict[str, Any] | None:
        result = raw.get("result")
        if isinstance(result, dict):
            return result

        text = cls._flatten_text(raw)
        payload = cls._extract_json_object(text)
        if isinstance(payload, dict):
            return payload
        return None

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        if not text:
            return None

        fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        candidates: list[str] = []
        if fenced:
            candidates.append(fenced.group(1))

        loose = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if loose:
            candidates.append(loose.group(1))

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
        return None

    @classmethod
    def _is_transient_click_miss(cls, raw: dict[str, Any]) -> bool:
        message = cls._flatten_text(raw).lower()
        return "no clickable element found" in message

    @classmethod
    def _flatten_text(cls, value: Any) -> str:
        if isinstance(value, dict):
            parts: list[str] = []
            for nested in value.values():
                text = cls._flatten_text(nested)
                if text:
                    parts.append(text)
            return "\n".join(parts)

        if isinstance(value, list):
            parts: list[str] = []
            for nested in value:
                text = cls._flatten_text(nested)
                if text:
                    parts.append(text)
            return "\n".join(parts)

        if isinstance(value, str):
            return value
        return ""

    async def get_clickable_alternatives(self, failed_selector: str) -> list[dict[str, str]]:
        """Extract clickable alternatives from the DOM when a selector fails."""
        try:
            snapshot = await self._call_and_track("take_snapshot", {})
            snapshot_text = self._snapshot_text(snapshot)
            lines = [line.strip() for line in snapshot_text.splitlines() if line.strip()]
            
            alternatives = []
            seen_uids = set()
            
            # Extract up to 5 clickable alternatives from the snapshot
            for line in lines:
                uid = self._extract_uid(line)
                if uid and uid not in seen_uids:
                    # Extract role and text from the line
                    if re.search(r"\b(button|link|link\s+button)\b", line, re.IGNORECASE):
                        # Extract text if present
                        text_match = re.search(r"['\"]([^'\"]+)['\"]", line)
                        text = text_match.group(1) if text_match else ""
                        
                        if text:
                            seen_uids.add(uid)
                            alternatives.append({
                                "uid": uid,
                                "text": text[:80],  # Limit to 80 chars
                                "description": f"Element with text '{text}'"
                            })
                        
                        if len(alternatives) >= 5:
                            break
            
            return alternatives
        except Exception:
            return []
