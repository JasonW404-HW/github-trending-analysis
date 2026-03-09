from typing import Any, cast

from src.analysis.trend_analyzer import TrendAnalyzer, analyze_trends


class DummyDb:
    def __init__(self):
        self.saved_today_data = None

    def get_yesterday_data(self, date):
        return [
            {"repo_name": "owner/a", "rank": 3, "stars": 100, "url": "https://x/a"},
            {"repo_name": "owner/drop", "rank": 10, "stars": 80, "url": "https://x/drop"},
        ]

    def save_today_data(self, date, data):
        self.saved_today_data = (date, data)

    def get_all_repo_details(self):
        return {
            "owner/a": {
                "summary": "A summary",
                "tags": ["ai"],
                "purpose_assessment": {"ok": True},
                "category_zh": "工具",
                "description": "desc",
                "use_case": "use",
                "solves": ["pain"],
                "category": "tool",
            },
            "owner/new": {
                "summary": "N summary",
                "tags": ["new"],
                "purpose_assessment": {},
                "category_zh": "应用",
            },
        }

    def get_category_stats(self, date):
        return [{"category": "tool", "category_zh": "工具", "count": 2}]



def test_calculate_deltas_for_existing_and_new_repo():
    analyzer = TrendAnalyzer(cast(Any, DummyDb()))
    today = [
        {"repo_name": "owner/a", "rank": 1, "stars": 130, "updated_at": "2026-03-09T00:00:00Z"},
        {"repo_name": "owner/new", "rank": 2, "stars": 40, "updated_at": "2026-03-09T01:00:00Z"},
    ]
    yesterday_map = {"owner/a": {"rank": 3, "stars": 100}}

    result = analyzer._calculate_deltas(today, yesterday_map)

    assert result[0]["rank_delta"] == 2
    assert result[0]["stars_delta"] == 30
    assert result[0]["stars_rate"] == 0.3
    assert result[1]["rank_delta"] == 0


def test_calculate_trends_builds_expected_sections():
    db = DummyDb()
    analyzer = TrendAnalyzer(cast(Any, db))
    today = [
        {"repo_name": "owner/a", "rank": 1, "stars": 130, "updated_at": "2026-03-09T01:00:00Z"},
        {"repo_name": "owner/new", "rank": 2, "stars": 220, "updated_at": "2026-03-09T02:00:00Z"},
    ]

    trends = analyzer.calculate_trends(today, "2026-03-09")

    assert trends["date"] == "2026-03-09"
    assert len(trends["top_20"]) == 2
    assert len(trends["new_entries"]) == 1
    assert len(trends["dropped_entries"]) == 1
    assert "summary" in trends["top_20"][0]
    assert db.saved_today_data is not None
    assert db.saved_today_data[0] == "2026-03-09"


def test_find_surging_repos_by_rate_or_delta():
    analyzer = TrendAnalyzer(cast(Any, DummyDb()))
    repos = [
        {"repo_name": "owner/rate", "stars_rate": 0.4, "stars_delta": 10},
        {"repo_name": "owner/delta", "stars_rate": 0.1, "stars_delta": 120},
        {"repo_name": "owner/none", "stars_rate": 0.1, "stars_delta": 10},
    ]

    surging = analyzer._find_surging_repos(repos, ai_summaries={})

    assert [repo["repo_name"] for repo in surging] == ["owner/rate", "owner/delta"]


def test_get_category_summary_formats_output():
    analyzer = TrendAnalyzer(cast(Any, DummyDb()))

    result = analyzer.get_category_summary("2026-03-09")

    assert result["date"] == "2026-03-09"
    assert result["categories"][0]["category"] == "tool"


def test_analyze_trends_helper_uses_passed_db_instance():
    db = DummyDb()
    today = [{"repo_name": "owner/a", "rank": 1, "stars": 100, "updated_at": "2026-03-09T00:00:00Z"}]

    result = analyze_trends(today, "2026-03-09", db=cast(Any, db), ai_summaries={})

    assert result["date"] == "2026-03-09"
