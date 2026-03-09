from src import cli_app


def test_normalize_repo_identifier_accepts_owner_repo():
    assert cli_app._normalize_repo_identifier("owner/repo") == "owner/repo"


def test_normalize_repo_identifier_accepts_github_url_and_git_suffix():
    assert (
        cli_app._normalize_repo_identifier("https://github.com/owner/repo.git")
        == "owner/repo"
    )


def test_normalize_repo_identifier_rejects_invalid_values():
    assert cli_app._normalize_repo_identifier("") is None
    assert cli_app._normalize_repo_identifier("not/a/valid/path") is None
    assert cli_app._normalize_repo_identifier("https://example.com/owner/repo") is None


def test_extract_repo_argument_supports_equals_and_space_forms():
    repo, error = cli_app._extract_repo_argument(["--repo", "owner/repo"])
    assert repo == "owner/repo"
    assert error is None

    repo2, error2 = cli_app._extract_repo_argument(["--repo=owner/repo"])
    assert repo2 == "owner/repo"
    assert error2 is None


def test_extract_repo_argument_validates_errors():
    repo, error = cli_app._extract_repo_argument(["--repo"])
    assert repo is None
    assert "缺少仓库值" in (error or "")

    repo2, error2 = cli_app._extract_repo_argument(["--repo=", "--repo", "a/b"])
    assert repo2 is None
    assert "缺少仓库值" in (error2 or "")

    repo3, error3 = cli_app._extract_repo_argument(["--repo", "a/b", "--repo", "c/d"])
    assert repo3 is None
    assert "仅允许指定一次" in (error3 or "")


def test_build_email_report_payload_counts_levels(monkeypatch):
    monkeypatch.setattr(cli_app, "PUSH_MIN_COMMERCIAL_LEVEL", "strong")

    payload = cli_app._build_email_report_payload(
        "2026-03-09",
        [
            {"commercial_value_level": "strong"},
            {"commercial_value_level": "weak"},
            {"commercial_value_level": "STRONG"},
        ],
    )

    assert payload["date"] == "2026-03-09"
    assert payload["strong_count"] == 2
    assert payload["weak_count"] == 1
    assert payload["total_candidates"] == 3
