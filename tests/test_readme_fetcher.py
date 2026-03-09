import base64
from typing import Any, cast

import requests

from src.github.readme_fetcher import ReadmeFetcher


class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data or {}

    @property
    def content(self):
        return self.text.encode("utf-8")

    @property
    def headers(self):
        return {}

    def raise_for_status(self):
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(f"status={self.status_code}", response=response)

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, response):
        self._response = response
        self.headers = {}

    def get(self, url, headers=None, timeout=30):
        return self._response



def test_extract_text_from_markdown_removes_common_syntax():
    fetcher = ReadmeFetcher(token="x")
    markdown = "# Title\nSome **bold** text with [link](https://example.com).\n```code```"

    text = fetcher._extract_text_from_markdown(markdown)

    assert "Title" in text
    assert "bold" in text
    assert "link" in text
    assert "code" not in text


def test_fetch_readme_decodes_base64_content(monkeypatch):
    fetcher = ReadmeFetcher(token="x")
    encoded = base64.b64encode("hello readme".encode("utf-8")).decode("utf-8")
    response = FakeResponse(json_data={"encoding": "base64", "content": encoded})

    monkeypatch.setattr(fetcher, "_request_with_retry", lambda **kwargs: response)

    content = fetcher.fetch_readme("owner", "repo")

    assert content == "hello readme"


def test_fetch_readme_returns_html_when_requested(monkeypatch):
    fetcher = ReadmeFetcher(token="x")
    response = FakeResponse(text="<h1>README</h1>")

    monkeypatch.setattr(fetcher, "_request_with_retry", lambda **kwargs: response)

    content = fetcher.fetch_readme("owner", "repo", html=True)

    assert content == "<h1>README</h1>"


def test_fetch_readme_summary_truncates_and_appends_ellipsis(monkeypatch):
    fetcher = ReadmeFetcher(token="x")
    monkeypatch.setattr(fetcher, "fetch_readme", lambda owner, repo: "word " * 100)

    summary = fetcher.fetch_readme_summary("owner", "repo", max_length=40)

    assert summary is not None
    assert summary.endswith("...")
    assert len(summary) <= 43


def test_batch_fetch_readmes_skips_invalid_repo_names(monkeypatch):
    fetcher = ReadmeFetcher(token="x")
    monkeypatch.setattr(fetcher, "fetch_readme_summary", lambda owner, repo: f"{owner}/{repo}")
    monkeypatch.setattr("time.sleep", lambda *_: None)

    summaries = fetcher.batch_fetch_readmes(
        [{"repo_name": "owner/repo"}, {"repo_name": "invalid"}, {"name": "missing/slash"}],
        delay=0,
    )

    assert summaries == {
        "owner/repo": "owner/repo",
        "missing/slash": "missing/slash",
    }


def test_request_with_retry_raises_http_error_for_429(monkeypatch):
    fetcher = ReadmeFetcher(token="x")

    response = FakeResponse(status_code=429, text="too many")
    fetcher.session = cast(Any, FakeSession(response))

    def fake_execute(operation, context):
        return operation()

    monkeypatch.setattr("src.github.readme_fetcher.execute_with_429_retry", fake_execute)

    try:
        fetcher._request_with_retry("https://example.com")
    except requests.HTTPError as error:
        assert "429" in str(error)
    else:
        raise AssertionError("Expected HTTPError")
