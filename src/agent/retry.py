from __future__ import annotations


def should_retry(step_attempt: int, max_attempts: int, has_error: bool) -> bool:
    if not has_error:
        return False
    return step_attempt < max_attempts
