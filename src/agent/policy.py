from __future__ import annotations

from src.browser.actions import BrowserAction


def to_browser_action(step: dict) -> BrowserAction:
    action = str(step.get("action", "")).strip().lower()
    selector = step.get("selector")
    url = step.get("url")
    wait_event = step.get("wait_event")

    if action == "navigate" and not url:
        action = "click" if selector else "wait"
    elif action == "open":
        action = "navigate"
    elif action == "fill":
        action = "type"
    elif action in {"press_key", "key", "keypress"}:
        action = "press"

    return BrowserAction(
        action_type=action,
        selector=selector,
        value=step.get("value"),
        url=url,
        wait_event=wait_event,
    )
