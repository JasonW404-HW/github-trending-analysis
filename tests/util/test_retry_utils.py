import requests

from src.util.retry_utils import execute_with_429_retry, is_429_error


class ErrorWithStatusCode(Exception):
    def __init__(self, status_code):
        super().__init__(f"status: {status_code}")
        self.status_code = status_code


def test_is_429_error_with_response_status():
    response = requests.Response()
    response.status_code = 429
    error = requests.HTTPError("too many requests", response=response)

    assert is_429_error(error) is True


def test_is_429_error_with_status_attr_or_message():
    assert is_429_error(ErrorWithStatusCode(429)) is True
    assert is_429_error(Exception("engine_overloaded_error")) is True
    assert is_429_error(Exception("bad request")) is False


def test_execute_with_429_retry_retries_until_success(monkeypatch):
    calls = {"count": 0}

    def op():
        calls["count"] += 1
        if calls["count"] < 3:
            response = requests.Response()
            response.status_code = 429
            raise requests.HTTPError("too many requests", response=response)
        return "ok"

    sleeps = []
    monkeypatch.setattr("time.sleep", lambda secs: sleeps.append(secs))

    result = execute_with_429_retry(op, context="test", cooldown_seconds=1, max_retries=5)

    assert result == "ok"
    assert calls["count"] == 3
    assert sleeps == [1, 1]


def test_execute_with_429_retry_raises_after_max_retries(monkeypatch):
    def op():
        response = requests.Response()
        response.status_code = 429
        raise requests.HTTPError("too many requests", response=response)

    monkeypatch.setattr("time.sleep", lambda *_: None)

    try:
        execute_with_429_retry(op, context="test", cooldown_seconds=0, max_retries=1)
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("Expected HTTPError to be raised after retries")


def test_execute_with_429_retry_does_not_retry_non_429():
    def op():
        raise ValueError("boom")

    try:
        execute_with_429_retry(op, context="test")
    except ValueError as error:
        assert str(error) == "boom"
    else:
        raise AssertionError("Expected ValueError to propagate")
