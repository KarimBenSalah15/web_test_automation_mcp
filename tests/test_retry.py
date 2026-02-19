from src.agent.retry import should_retry


def test_should_retry_when_error_and_below_limit() -> None:
    assert should_retry(step_attempt=1, max_attempts=2, has_error=True)


def test_should_not_retry_when_no_error() -> None:
    assert not should_retry(step_attempt=1, max_attempts=2, has_error=False)


def test_should_not_retry_when_limit_reached() -> None:
    assert not should_retry(step_attempt=2, max_attempts=2, has_error=True)
