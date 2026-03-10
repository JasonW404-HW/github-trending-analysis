from src.pipeline.models import AnalysisRunResult, AnalysisRunStats, RepoSelectionResult
from src.trending_workflow import TrendingWorkflow


class DummyFetcher:
    def __init__(self):
        self.calls = []

    def fetch_with_cache(self, **kwargs):
        self.calls.append(kwargs)
        return [{"repo_name": "owner/repo", "rank": 1}], True

    def fetch_single_repository(self, repo_identifier, rank):
        return {"repo_name": repo_identifier, "rank": rank}


class DummyDb:
    def __init__(self):
        self.saved = []

    def save_today_data(self, date, repos):
        self.saved.append((date, repos))


class DummyAnalysisStep:
    def __init__(self):
        self.input_repos = None

    def analyze(self, repos):
        self.input_repos = repos
        return AnalysisRunResult(
            summary_map={"owner/repo": {"summary": "ok"}},
            stats=AnalysisRunStats(
                cached_count=0,
                pending_count=1,
                success_count=1,
                fallback_count=0,
            ),
        )


class DummyTrendAnalyzer:
    def __init__(self):
        self.calls = []

    def calculate_trends(self, repos, date, ai_summaries):
        self.calls.append((repos, date, ai_summaries))
        return {"date": date, "top_20": repos}


def test_fetch_rankings_delegates_to_fetcher_with_defaults():
    db = DummyDb()
    fetcher = DummyFetcher()
    workflow = TrendingWorkflow(
        db=db,
        fetcher=fetcher,
        analysis_step=DummyAnalysisStep(),
        trend_analyzer=DummyTrendAnalyzer(),
    )

    repos, cache_hit = workflow.fetch_rankings("2026-03-09", limit=20, cache_minutes=10)

    assert cache_hit is True
    assert repos[0]["repo_name"] == "owner/repo"
    assert fetcher.calls[0]["sort_by"] == "stars"


def test_persist_snapshot_saves_to_database():
    db = DummyDb()
    workflow = TrendingWorkflow(
        db=db,
        fetcher=DummyFetcher(),
        analysis_step=DummyAnalysisStep(),
        trend_analyzer=DummyTrendAnalyzer(),
    )

    workflow.persist_snapshot("2026-03-09", [{"repo_name": "owner/repo"}])

    assert db.saved == [("2026-03-09", [{"repo_name": "owner/repo"}])]


def test_fetch_single_repository_delegates_to_fetcher():
    workflow = TrendingWorkflow(
        db=DummyDb(),
        fetcher=DummyFetcher(),
        analysis_step=DummyAnalysisStep(),
        trend_analyzer=DummyTrendAnalyzer(),
    )

    repo = workflow.fetch_single_repository("owner/repo")

    assert repo == {"repo_name": "owner/repo", "rank": 1}


def test_analyze_selected_delegates_to_analysis_step():
    analysis_step = DummyAnalysisStep()
    workflow = TrendingWorkflow(
        db=DummyDb(),
        fetcher=DummyFetcher(),
        analysis_step=analysis_step,
        trend_analyzer=DummyTrendAnalyzer(),
    )

    selection = RepoSelectionResult(
        repos=[{"repo_name": "owner/repo"}],
        total_count=1,
        selected_count=1,
        keywords=["ai"],
        match_mode="any",
    )

    result = workflow.analyze_selected(selection)

    assert analysis_step.input_repos == [{"repo_name": "owner/repo"}]
    assert result.stats.success_count == 1


def test_run_executes_full_pipeline_in_order(monkeypatch):
    db = DummyDb()
    fetcher = DummyFetcher()
    analysis_step = DummyAnalysisStep()
    trend_analyzer = DummyTrendAnalyzer()
    workflow = TrendingWorkflow(
        db=db,
        fetcher=fetcher,
        analysis_step=analysis_step,
        trend_analyzer=trend_analyzer,
    )

    selection = RepoSelectionResult(
        repos=[{"repo_name": "owner/repo"}],
        total_count=1,
        selected_count=1,
        keywords=[],
        match_mode="any",
    )

    monkeypatch.setattr(workflow, "select_analysis_targets", lambda repos, top_n: selection)

    result = workflow.run("2026-03-09", fetch_limit=50, top_n=5)

    assert result.date == "2026-03-09"
    assert result.cache_hit is True
    assert result.selection.selected_count == 1
    assert result.analysis.stats.success_count == 1
    assert result.trends["date"] == "2026-03-09"
    assert len(db.saved) == 1
