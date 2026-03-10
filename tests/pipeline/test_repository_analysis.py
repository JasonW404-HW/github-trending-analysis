from typing import Any, cast

from src.pipeline.repository_analysis import RepositoryAnalysisStep
from src.config import MODEL


class DummyDb:
    def __init__(self, cache=None):
        self.cache = cache or {}
        self.saved = []
        self.states = {}
        self.index_states = {}
        self.runs = []

    def get_repo_details_if_fresh(self, repo_name, repo_updated_at, prompt_hash):
        return self.cache.get(repo_name)

    def get_repo_details(self, repo_name):
        return self.cache.get(repo_name)

    def save_repo_detail(self, summary, verbose=False):
        self.saved.append((summary, verbose))

    def get_repo_analysis_state(self, repo_name):
        return self.states.get(repo_name)

    def upsert_repo_analysis_state(self, **kwargs):
        self.states[kwargs["repo_name"]] = dict(kwargs)

    def insert_repo_analysis_run(self, **kwargs):
        self.runs.append(dict(kwargs))

    def get_repo_index_state(self, repo_name):
        return self.index_states.get(repo_name)

    def upsert_repo_index_state(self, **kwargs):
        self.index_states[kwargs["repo_name"]] = dict(kwargs)


class DummyReadmeFetcher:
    def __init__(self, summaries):
        self.summaries = summaries
        self.calls = []

    def batch_fetch_readmes(self, repos, delay):
        self.calls.append((repos, delay))
        return self.summaries


class DummyActivityFetcher:
    def __init__(self, activities):
        self.activities = activities
        self.calls = []

    def batch_fetch_recent_activity(self, **kwargs):
        self.calls.append(kwargs)
        return self.activities


class DummySummarizer:
    def __init__(self, extra_prompt=None):
        self.extra_prompt = extra_prompt

    def summarize_and_classify(self, repos, on_success=None):
        results = []
        for repo in repos:
            summary = {
                "repo_name": repo["repo_name"],
                "summary": f"summary for {repo['repo_name']}",
                "fallback": repo.get("repo_name") == "owner/fallback",
            }
            if on_success:
                on_success(dict(summary))
            results.append(summary)
        return results


def test_build_prompt_hash_default_and_non_default():
    assert RepositoryAnalysisStep._build_prompt_hash("") == "default"
    digest = RepositoryAnalysisStep._build_prompt_hash("custom prompt", "salt")
    assert len(digest) == 16


def test_analyze_returns_only_cached_when_all_hit():
    db = DummyDb(cache={"owner/a": {"repo_name": "owner/a", "summary": "cached"}})
    step = RepositoryAnalysisStep(
        db=cast(Any, db),
        readme_fetcher=cast(Any, DummyReadmeFetcher({})),
        activity_fetcher=cast(Any, DummyActivityFetcher({})),
        summarizer_factory=cast(Any, DummySummarizer),
    )

    result = step.analyze([{"repo_name": "owner/a", "updated_at": "2026-01-01"}])

    assert result.summary_map["owner/a"]["summary"] == "cached"
    assert result.stats.cached_count == 1
    assert result.stats.pending_count == 0
    assert db.saved == []


def test_analyze_runs_full_flow_for_pending_repositories():
    db = DummyDb(cache={"owner/cached": {"repo_name": "owner/cached", "summary": "hit"}})
    readme_fetcher = DummyReadmeFetcher({"owner/new": "readme summary"})
    activity_fetcher = DummyActivityFetcher(
        {
            "owner/new": {
                "issues": [{"id": 1}],
                "pull_requests": [{"id": 2}],
                "focus_issue_threads": ["issue thread"],
                "focus_pr_threads": ["pr thread"],
                "detail_last_comments": "3",
                "window_days": "14",
            }
        }
    )
    step = RepositoryAnalysisStep(
        db=cast(Any, db),
        readme_fetcher=cast(Any, readme_fetcher),
        activity_fetcher=cast(Any, activity_fetcher),
        summarizer_factory=cast(Any, DummySummarizer),
        fetch_delay=0,
        extra_prompt="custom",
    )

    repos = [
        {"repo_name": "owner/cached", "updated_at": "2026-01-01"},
        {"repo_name": "owner/new", "updated_at": "2026-01-02"},
    ]

    result = step.analyze(repos)

    assert set(result.summary_map.keys()) == {"owner/cached", "owner/new"}
    assert result.summary_map["owner/new"]["summary"] == "summary for owner/new"
    assert result.stats.cached_count == 1
    assert result.stats.pending_count == 1
    assert result.stats.success_count == 1
    assert result.stats.fallback_count == 0
    assert len(db.saved) == 1
    assert db.saved[0][0]["repo_name"] == "owner/new"
    assert readme_fetcher.calls
    assert activity_fetcher.calls


def test_analyze_counts_fallback_summaries():
    db = DummyDb()
    step = RepositoryAnalysisStep(
        db=cast(Any, db),
        readme_fetcher=cast(Any, DummyReadmeFetcher({})),
        activity_fetcher=cast(Any, DummyActivityFetcher({})),
        summarizer_factory=cast(Any, DummySummarizer),
        fetch_delay=0,
    )

    result = step.analyze([{"repo_name": "owner/fallback", "updated_at": "2026-01-01"}])

    assert result.stats.success_count == 0
    assert result.stats.fallback_count == 1
    assert result.summary_map["owner/fallback"]["fallback"] is True


def test_attach_recent_activity_handles_invalid_payloads():
    db = DummyDb()
    activity_fetcher = DummyActivityFetcher({"owner/new": "invalid"})
    step = RepositoryAnalysisStep(
        db=cast(Any, db),
        readme_fetcher=cast(Any, DummyReadmeFetcher({})),
        activity_fetcher=cast(Any, activity_fetcher),
        summarizer_factory=cast(Any, DummySummarizer),
    )

    repos = [{"repo_name": "owner/new"}]
    step._attach_recent_activity(repos)

    assert repos[0]["recent_issues"] == []
    assert repos[0]["recent_pull_requests"] == []
    assert repos[0]["focus_issue_threads"] == []
    assert repos[0]["focus_pr_threads"] == []


def test_analyze_reuses_previous_result_when_low_change_and_within_interval():
    db = DummyDb(
        cache={
            "owner/reuse": {
                "repo_name": "owner/reuse",
                "summary": "cached summary",
                "repo_updated_at": "2026-01-01T00:00:00Z",
                "prompt_hash": "abcd",
            }
        }
    )
    db.states["owner/reuse"] = {
        "repo_name": "owner/reuse",
        "last_analyzed_at": "2099-01-01T00:00:00Z",
        "last_prompt_hash": RepositoryAnalysisStep._build_prompt_hash("", strategy_salt="activity-v2|30|6|6|2|2|4"),
        "last_model": MODEL,
        "last_repo_updated_at": "2026-01-01T00:00:00Z",
        "last_rank_bucket": "other",
        "last_change_score": 1,
    }

    step = RepositoryAnalysisStep(
        db=cast(Any, db),
        readme_fetcher=cast(Any, DummyReadmeFetcher({})),
        activity_fetcher=cast(Any, DummyActivityFetcher({"owner/reuse": {"issues": [], "pull_requests": []}})),
        summarizer_factory=cast(Any, DummySummarizer),
        analysis_interval_days=30,
        change_score_threshold=99,
    )

    result = step.analyze([
        {
            "repo_name": "owner/reuse",
            "updated_at": "2026-01-01T00:00:00Z",
            "rank": 10,
        }
    ])

    assert result.stats.pending_count == 0
    assert result.summary_map["owner/reuse"]["summary"] == "cached summary"
    assert db.saved == []
